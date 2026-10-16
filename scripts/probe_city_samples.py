#!/usr/bin/env python3
"""Probe free US City Network samples — reliability without spending.

Read-only operator tool. Hits the public (or local) catalog + every city's
fixed-address sample. Exit 0 only when catalog + all samples return healthy
JSON. Stable stdout JSON for cron / change detection.

    .venv/bin/python scripts/probe_city_samples.py
    .venv/bin/python scripts/probe_city_samples.py --base https://x402-mcp.onrender.com
    .venv/bin/python scripts/probe_city_samples.py --codes mn,sea --timeout 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_BASE = "https://x402-mcp.onrender.com"
UA = "x402-mcp-city-sample-probe/1.0 (operator; read-only)"


def _normalize_base(base: str) -> str:
    return base.rstrip("/")


def evaluate_catalog(body: dict[str, Any]) -> dict[str, Any]:
    """Validate /us/cities payload shape without network I/O."""
    cities = body.get("cities")
    if not isinstance(cities, list) or not cities:
        return {
            "ok": False,
            "error": "empty_or_missing_cities",
            "city_count": 0,
            "codes": [],
        }
    codes: list[str] = []
    for c in cities:
        if not isinstance(c, dict) or not c.get("code"):
            return {
                "ok": False,
                "error": "city_row_missing_code",
                "city_count": len(cities),
                "codes": codes,
            }
        codes.append(str(c["code"]))
        if not c.get("sample_url") or not c.get("paid_url"):
            return {
                "ok": False,
                "error": f"city_{c['code']}_missing_urls",
                "city_count": len(cities),
                "codes": codes,
            }
    return {
        "ok": True,
        "error": None,
        "city_count": len(cities),
        "codes": codes,
        "network": body.get("network"),
        "price": body.get("price"),
    }


def evaluate_sample(body: dict[str, Any], *, city_code: str) -> dict[str, Any]:
    """Validate free sample JSON (same envelope HTTP and MCP should share)."""
    if body.get("error"):
        return {
            "ok": False,
            "city": city_code,
            "error": body.get("error"),
            "detail": body.get("detail"),
        }
    if body.get("sample") is not True:
        return {"ok": False, "city": city_code, "error": "missing_sample_flag"}
    if body.get("city") != city_code:
        return {
            "ok": False,
            "city": city_code,
            "error": "city_mismatch",
            "got": body.get("city"),
        }
    report = body.get("report")
    if not isinstance(report, dict):
        return {"ok": False, "city": city_code, "error": "missing_report"}
    next_hop = body.get("next")
    has_next = isinstance(next_hop, dict) and bool(
        next_hop.get("paid_url") or next_hop.get("mcp_tool") or next_hop.get("http")
    )
    return {
        "ok": True,
        "city": city_code,
        "error": None,
        "sample_address": body.get("sample_address"),
        "has_next_handoff": has_next,
        "report_keys": sorted(report.keys())[:20],
    }


def probe(
    base: str,
    *,
    codes: list[str] | None = None,
    timeout: float = 25.0,
) -> dict[str, Any]:
    """Fetch catalog + samples. Pure HTTP; no payment."""
    base = _normalize_base(base)
    out: dict[str, Any] = {
        "base": base,
        "catalog": None,
        "samples": [],
        "ok": False,
        "failed": [],
    }
    headers = {"User-Agent": UA, "Accept": "application/json"}
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        cat_resp = client.get(f"{base}/us/cities")
        try:
            cat_body = cat_resp.json()
        except Exception:
            cat_body = {"_raw": cat_resp.text[:200]}
        cat_eval = evaluate_catalog(cat_body if isinstance(cat_body, dict) else {})
        cat_eval["http_status"] = cat_resp.status_code
        if cat_resp.status_code != 200:
            cat_eval["ok"] = False
            cat_eval["error"] = cat_eval.get("error") or f"http_{cat_resp.status_code}"
        out["catalog"] = cat_eval
        if not cat_eval["ok"]:
            out["failed"].append("catalog")
            return out

        want = {c.lower() for c in codes} if codes else None
        cities = cat_body.get("cities") or []
        for row in cities:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").lower()
            if not code:
                continue
            if want is not None and code not in want:
                continue
            url = str(row.get("sample_url") or "")
            if not url:
                out["samples"].append(
                    {"ok": False, "city": code, "error": "missing_sample_url"}
                )
                out["failed"].append(code)
                continue
            try:
                resp = client.get(url)
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                if resp.status_code != 200:
                    ev = {
                        "ok": False,
                        "city": code,
                        "error": f"http_{resp.status_code}",
                        "url": url,
                    }
                else:
                    ev = evaluate_sample(
                        body if isinstance(body, dict) else {}, city_code=code
                    )
                    ev["url"] = url
                    ev["http_status"] = resp.status_code
            except Exception as exc:  # noqa: BLE001
                ev = {
                    "ok": False,
                    "city": code,
                    "error": "request_failed",
                    "detail": f"{type(exc).__name__}: {exc}"[:200],
                    "url": url,
                }
            out["samples"].append(ev)
            if not ev.get("ok"):
                out["failed"].append(code)

    out["ok"] = not out["failed"] and bool(out["samples"])
    out["sample_count"] = len(out["samples"])
    out["pass_count"] = sum(1 for s in out["samples"] if s.get("ok"))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default=DEFAULT_BASE, help="storefront origin")
    p.add_argument(
        "--codes",
        default="",
        help="comma-separated city codes (default: all from catalog)",
    )
    p.add_argument("--timeout", type=float, default=25.0)
    args = p.parse_args(argv)
    codes = [c.strip() for c in args.codes.split(",") if c.strip()] or None
    result = probe(args.base, codes=codes, timeout=args.timeout)
    # Stable key order for humans; values only (no timestamps).
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
