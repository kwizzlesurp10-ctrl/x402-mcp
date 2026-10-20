"""Read the CDP Bazaar catalog as a demand instrument, before building anything.

`docs/PRODUCT-FOCUS.md` records nine days spent building on endpoints the
repo's own data said to abandon, because the instrument existed and was not
read. This is the instrument that did not exist at all: a way to ask "does
anyone pay for things like X, and is it one wired-in integration or a crowd of
one-shot probes" *before* writing product code.

The discovery API returns, per resource and unauthenticated, a `quality` block
with `l30DaysTotalCalls` and `l30DaysUniquePayers`. Calls-per-payer is the
column that matters: a catalog scan on 2026-08-03 found one seller listing 993
endpoints and earning $0.00, while another earned from 23,368 calls by a
single payer. Endpoint count is not a growth lever on this rail.

Operator tooling. Read-only, unauthenticated, spends nothing, writes nothing.
Deliberately a script and not a route - app/openapi_spec.py is an allowlist and
a new route would be private by default.

    .venv\\Scripts\\python.exe scripts/market_scan.py --query property --top 20
    .venv\\Scripts\\python.exe scripts/market_scan.py --min-payers 50 --top 30
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402

PAGE_SIZE = 100
USDC_DECIMALS = 1_000_000

# Some listings carry placeholder amounts rather than a real price (variable
# pricing, or a sentinel). Revenue estimated from those is meaningless, so they
# are flagged rather than silently dropped.
PRICE_OUTLIER_ATOMIC = 1_000_000_000


def fetch_all(url: str, *, timeout: float = 30.0) -> list[dict[str, Any]]:
    """Page the discovery API to exhaustion. No API key required."""
    headers = {
        "User-Agent": (
            f"x402-mcp-market-scan/1.0 (operator research; {settings.contact_email})"
        )
    }
    resources: list[dict[str, Any]] = []
    offset = 0
    with httpx.Client(timeout=timeout, headers=headers) as client:
        while True:
            resp = client.get(url, params={"limit": PAGE_SIZE, "offset": offset})
            resp.raise_for_status()
            body = resp.json()
            page = body.get("items") or body.get("resources") or body.get("data") or []
            resources.extend(page)

            pagination = body.get("pagination") or {}
            total = pagination.get("total")
            offset += PAGE_SIZE
            if not page:
                break
            if total is not None and offset >= int(total):
                break
            if total is None and len(page) < PAGE_SIZE:
                break
    return resources


def _first_amount_atomic(resource: dict[str, Any]) -> int | None:
    accepts = resource.get("accepts") or []
    if not accepts:
        return None
    try:
        return int(accepts[0].get("amount"))
    except (TypeError, ValueError):
        return None


def summarize(resource: dict[str, Any]) -> dict[str, Any]:
    """One row: price, demand, and the calls-per-payer discriminator."""
    quality = resource.get("quality") or {}
    calls = quality.get("l30DaysTotalCalls")
    payers = quality.get("l30DaysUniquePayers")
    atomic = _first_amount_atomic(resource)

    price = None if atomic is None else atomic / USDC_DECIMALS
    outlier = atomic is not None and atomic >= PRICE_OUTLIER_ATOMIC

    calls_i = int(calls) if isinstance(calls, (int, float)) else None
    payers_i = int(payers) if isinstance(payers, (int, float)) else None

    return {
        "resource": resource.get("resource"),
        "description": (resource.get("description") or "")[:120],
        "price_usd": price,
        "price_outlier": outlier,
        "calls_30d": calls_i,
        "unique_payers_30d": payers_i,
        # None rather than ZeroDivisionError: a resource with calls but no
        # recorded payers is a real state in this catalog.
        "calls_per_payer": (
            round(calls_i / payers_i, 1) if calls_i and payers_i else None
        ),
        "est_30d_revenue": (
            None if (price is None or calls_i is None or outlier) else round(price * calls_i, 2)
        ),
    }


def matches(row: dict[str, Any], queries: list[str]) -> bool:
    if not queries:
        return True
    hay = f"{row.get('resource') or ''} {row.get('description') or ''}".lower()
    return any(q.lower() in hay for q in queries)


def price_ladder(rows: list[dict[str, Any]]) -> dict[str, float]:
    prices = sorted(
        r["price_usd"] for r in rows if r["price_usd"] is not None and not r["price_outlier"]
    )
    if not prices:
        return {}

    def pct(p: float) -> float:
        return prices[min(len(prices) - 1, int(len(prices) * p))]

    return {
        "p10": pct(0.10),
        "p25": pct(0.25),
        "median": pct(0.50),
        "p75": pct(0.75),
        "p90": pct(0.90),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="case-insensitive substring over resource+description (repeatable)",
    )
    parser.add_argument("--min-payers", type=int, default=0)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--base-url",
        default=settings.public_base_url,
        help=(
            "origin to match this repo's own listings against. Defaults to "
            "PUBLIC_BASE_URL, which is localhost on an operator machine and "
            "will match nothing - pass the deployed origin."
        ),
    )
    args = parser.parse_args()

    raw = fetch_all(settings.cdp_discovery_url)
    rows = [summarize(r) for r in raw]

    base = args.base_url.rstrip("/")
    ours = [r for r in rows if base and base in (r["resource"] or "")]
    loopback = any(h in base for h in ("localhost", "127.0.0.1", "0.0.0.0"))

    selected = [
        r
        for r in rows
        if matches(r, args.query) and (r["unique_payers_30d"] or 0) >= args.min_payers
    ]
    selected.sort(key=lambda r: (r["est_30d_revenue"] or 0, r["calls_30d"] or 0), reverse=True)

    if args.json:
        print(json.dumps({"matched": selected[: args.top], "ours": ours}, indent=2))
        return 0

    print(f"scanned {len(rows)} catalog resources")
    print(
        "NOTE: est_30d_revenue is calls x LISTED price. It is meaningless for "
        "variable-price endpoints; those are flagged price_outlier and excluded."
    )
    ladder = price_ladder(rows)
    if ladder:
        print("price ladder: " + "  ".join(f"{k}=${v:g}" for k, v in ladder.items()))

    print(f"\n--- matched ({len(selected)}), top {args.top} ---")
    for r in selected[: args.top]:
        flag = " [price-outlier]" if r["price_outlier"] else ""
        print(
            f"{r['est_30d_revenue'] if r['est_30d_revenue'] is not None else '?':>9} "
            f"${r['price_usd'] if r['price_usd'] is not None else '?':<8} "
            f"calls={r['calls_30d']} payers={r['unique_payers_30d']} "
            f"c/p={r['calls_per_payer']}{flag}  {r['resource']}"
        )

    print("\n--- this repo's own listings ---")
    if not ours and loopback:
        print(
            f"  {base} is a loopback origin and cannot appear in a public "
            f"catalog. Re-run with --base-url <deployed origin>."
        )
    elif not ours:
        print(f"  none found for {base} (not catalogued yet)")
    for r in ours:
        print(
            f"  calls={r['calls_30d']} payers={r['unique_payers_30d']} "
            f"c/p={r['calls_per_payer']} ${r['price_usd']}  {r['resource']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
