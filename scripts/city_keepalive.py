#!/usr/bin/env python3
"""City-network keepalive settles — only access-barrier products.

PRODUCT-FOCUS: do **not** spend keepalive on Pulse composite or /base/tx-decision.
This script settles only MN + US city property-check URLs (and optional allowlist).

Uses local buyer key only (never on Render). Reads public /demand so you can
skip cities that already fail the reverse clause (0 external @ high challenges)
unless --force.

    # dry-run (default): print targets, spend nothing
    .venv/bin/python scripts/city_keepalive.py

    # settle mn + cities still under challenge threshold or with any external sale
    BUYER_ENV=/home/keef/secrets/x402-buyer.env \\
      .venv/bin/python scripts/city_keepalive.py --execute

    # only Minneapolis canonical path
    .venv/bin/python scripts/city_keepalive.py --codes mn --execute
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_BASE = "https://x402-mcp.onrender.com"
# Reverse-clause style guard from docs/PRODUCT-FOCUS.md (operator override via --force).
DEFAULT_MAX_CHALLENGES_AT_ZERO_EXTERNAL = 600
# Demoted free-RPC products — never keep alive here.
BLOCKED_RESOURCE_SUBSTR = (
    "base-tx-decision",
    "base/tx-decision",
    "base-finality",
    "base/finality",
    "swarm/products",
    "d22bbf5f3c4b4666a6f80980c7bc7c50",  # pinned pulse product id prefix area
)


def load_buyer_env(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"buyer env not found: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def demand_index(demand_body: dict[str, Any] | list[Any]) -> dict[str, dict[str, Any]]:
    """Map resource key → demand row."""
    rows = demand_body.get("resources") if isinstance(demand_body, dict) else demand_body
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = str(r.get("resource") or r.get("resource_key") or r.get("product_id") or "")
        if key:
            out[key] = r
    return out


def demand_for_city(index: dict[str, dict[str, Any]], code: str) -> dict[str, Any] | None:
    code = code.lower()
    # Prefer the demand key that actually receives traffic.
    # MN canonical path records as mn-property-check; network alias is separate.
    if code == "mn":
        candidates = (
            "mn-property-check",
            "us-city-mn-property-check",
        )
    else:
        candidates = (f"us-city-{code}-property-check",)
    for c in candidates:
        if c in index:
            return index[c]
    for key, row in index.items():
        kl = key.lower()
        if code in kl and "property" in kl:
            return row
    return None


def should_keepalive(
    row: dict[str, Any] | None,
    *,
    max_challenges_at_zero_external: int,
    force: bool,
) -> tuple[bool, str]:
    if force:
        return True, "force"
    if row is None:
        return True, "no_demand_row_yet"
    ext = int(row.get("sales_external") or 0)
    ch = int(row.get("challenges_served") or row.get("challenges") or 0)
    if ext > 0:
        return True, f"has_external_sales={ext}"
    if ch >= max_challenges_at_zero_external:
        return (
            False,
            f"reverse_clause_risk challenges={ch} external=0 "
            f"(threshold={max_challenges_at_zero_external})",
        )
    return True, f"under_threshold challenges={ch} external=0"


def build_targets(
    cities: list[dict[str, Any]],
    *,
    base: str,
    codes: list[str] | None,
    demand: dict[str, dict[str, Any]],
    max_challenges_at_zero_external: int,
    force: bool,
    include_canonical_mn: bool = True,
) -> list[dict[str, Any]]:
    """Build settle URLs for allowed city products only."""
    want = {c.lower() for c in codes} if codes else None
    targets: list[dict[str, Any]] = []

    if include_canonical_mn and (want is None or "mn" in want):
        row = demand_for_city(demand, "mn")
        ok, reason = should_keepalive(
            row,
            max_challenges_at_zero_external=max_challenges_at_zero_external,
            force=force,
        )
        sample = "1700 Penn Ave N"
        url = f"{base.rstrip('/')}/mn/property-check?address={quote(sample)}"
        targets.append(
            {
                "code": "mn",
                "label": "mn-canonical",
                "url": url,
                "keepalive": ok,
                "reason": reason,
                "demand": {
                    "challenges": (row or {}).get("challenges_served"),
                    "sales_external": (row or {}).get("sales_external"),
                },
            }
        )

    for c in cities:
        code = str(c.get("code") or "").lower()
        if not code:
            continue
        if want is not None and code not in want:
            continue
        # Skip duplicate mn network path if canonical already included unless forced codes
        if code == "mn" and include_canonical_mn and want is None:
            continue
        paid = c.get("paid_url") or f"{base.rstrip('/')}/us/{code}/property-check"
        addr = c.get("sample_address") or "1 Main St"
        url = f"{paid}?address={quote(str(addr))}"
        # Safety: never target demoted surfaces even if catalog drifts
        if any(b in url for b in BLOCKED_RESOURCE_SUBSTR):
            continue
        row = demand_for_city(demand, code)
        ok, reason = should_keepalive(
            row,
            max_challenges_at_zero_external=max_challenges_at_zero_external,
            force=force,
        )
        targets.append(
            {
                "code": code,
                "label": f"us-city-{code}",
                "url": url,
                "keepalive": ok,
                "reason": reason,
                "demand": {
                    "challenges": (row or {}).get("challenges_served"),
                    "sales_external": (row or {}).get("sales_external"),
                },
            }
        )
    return targets


async def settle_one(url: str, *, max_price_usdc: float) -> dict[str, Any]:
    from app.models import PayAndFetchInput
    from app import x402_services

    try:
        result = await x402_services.pay_and_fetch(
            PayAndFetchInput(url=url, method="GET", max_price_usdc=max_price_usdc)
        )
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "ok": False, "error": str(exc)[:300]}
    return {
        "url": url,
        "ok": bool(result.get("payment_settled")),
        "status_code": result.get("status_code"),
        "payment_settled": result.get("payment_settled"),
        "body_preview": str(result.get("body") or "")[:160],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument("--codes", default="", help="comma city codes (default: all + mn canonical)")
    p.add_argument("--execute", action="store_true", help="actually settle (default dry-run)")
    p.add_argument("--force", action="store_true", help="ignore reverse-clause threshold")
    p.add_argument(
        "--max-challenges-at-zero-external",
        type=int,
        default=DEFAULT_MAX_CHALLENGES_AT_ZERO_EXTERNAL,
    )
    p.add_argument(
        "--buyer-env",
        default=os.environ.get("BUYER_ENV", "/home/keef/secrets/x402-buyer.env"),
    )
    p.add_argument("--max-price-usdc", type=float, default=0.05)
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args(argv)

    base = args.base.rstrip("/")
    codes = [c.strip() for c in args.codes.split(",") if c.strip()] or None
    headers = {
        "User-Agent": "x402-mcp-city-keepalive/1.0 (operator)",
        "Accept": "application/json",
    }

    with httpx.Client(timeout=args.timeout, headers=headers) as client:
        cities_body = client.get(f"{base}/us/cities").json()
        try:
            demand_body = client.get(f"{base}/demand").json()
        except Exception:
            demand_body = {"resources": []}

    cities = cities_body.get("cities") or []
    didx = demand_index(demand_body)
    targets = build_targets(
        cities,
        base=base,
        codes=codes,
        demand=didx,
        max_challenges_at_zero_external=args.max_challenges_at_zero_external,
        force=args.force,
    )

    plan = {
        "base": base,
        "execute": bool(args.execute),
        "force": bool(args.force),
        "targets": targets,
        "will_settle": [t for t in targets if t["keepalive"]],
        "skipped": [t for t in targets if not t["keepalive"]],
    }
    print(json.dumps({k: plan[k] for k in ("base", "execute", "force")}, indent=2))
    print(
        json.dumps(
            {
                "will_settle_count": len(plan["will_settle"]),
                "skipped_count": len(plan["skipped"]),
                "will_settle": plan["will_settle"],
                "skipped": plan["skipped"],
            },
            indent=2,
            sort_keys=True,
        )
    )

    if not args.execute:
        print("dry-run only — pass --execute to settle")
        return 0

    load_buyer_env(Path(args.buyer_env))
    if not os.environ.get("EVM_PRIVATE_KEY"):
        print("FAIL: EVM_PRIVATE_KEY missing after loading buyer env", file=sys.stderr)
        return 2

    async def _run() -> list[dict[str, Any]]:
        out = []
        for t in plan["will_settle"]:
            print("settling", t["label"], t["url"])
            r = await settle_one(t["url"], max_price_usdc=args.max_price_usdc)
            r["label"] = t["label"]
            out.append(r)
            print(json.dumps({k: r[k] for k in r if k != "body_preview"}, indent=2))
        return out

    results = asyncio.run(_run())
    ok = sum(1 for r in results if r.get("ok"))
    Path("/tmp/x402_city_keepalive.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    print(f"done ok={ok}/{len(results)} detail=/tmp/x402_city_keepalive.json")
    return 0 if ok == len(results) and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
