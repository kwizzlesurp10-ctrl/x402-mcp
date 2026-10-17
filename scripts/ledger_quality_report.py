#!/usr/bin/env python3
"""Dry-run report: raw revenue ledger vs verified external revenue.

Read-only. Never writes to the ledger or Redis.

  # from the live deployment (newest 1000 rows)
  python scripts/ledger_quality_report.py --url https://x402-mcp.onrender.com
  # from an exported JSON array or a jsonl file
  python scripts/ledger_quality_report.py --file revenue.json
  # also check each real hash on Base for a USDC transfer to a project payTo and
  # print exclusion candidates (add them to app/revenue_exclusions.json by hand)
  python scripts/ledger_quality_report.py --url ... --onchain
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ledger_quality  # noqa: E402

USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _load(args: argparse.Namespace) -> list[dict]:
    if args.url:
        req = urllib.request.Request(
            args.url.rstrip("/") + "/ledger/revenue", headers={"User-Agent": "ledger-report/1"}
        )
        return json.load(urllib.request.urlopen(req, timeout=60))
    text = Path(args.file).read_text(encoding="utf-8").strip()
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _receipt(rpc: str, tx: str) -> dict | None:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionReceipt", "params": [tx]}
    ).encode()
    req = urllib.request.Request(rpc, body, {"Content-Type": "application/json", "User-Agent": "curl/8"})
    return json.load(urllib.request.urlopen(req, timeout=30)).get("result")


def _pays_project(rc: dict) -> bool:
    for lg in rc.get("logs", []):
        t = lg.get("topics", [])
        if lg.get("address", "").lower() == USDC and len(t) == 3 and t[0] == TRANSFER:
            if "0x" + t[2][-40:].lower() in ledger_quality.PROJECT_PAYTO_ADDRESSES:
                return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url")
    src.add_argument("--file")
    ap.add_argument("--operator-wallets", default="", help="comma-separated; defaults to OPERATOR_WALLETS config")
    ap.add_argument("--onchain", action="store_true")
    ap.add_argument("--rpc", default="https://mainnet.base.org")
    args = ap.parse_args()

    rows = _load(args)
    wallets = (
        {w.strip().lower() for w in args.operator_wallets.split(",") if w.strip()}
        if args.operator_wallets
        else None
    )
    # Rows served by /ledger/revenue already carry is_operator_settle from the
    # server's OPERATOR_WALLETS; honour it when no wallets are given locally.
    if wallets is None:
        wallets = {
            str(r.get("payer")).lower()
            for r in rows
            if r.get("is_operator_settle") is True and r.get("payer")
        }
    annotated = ledger_quality.annotate_revenue_rows(rows, operator_wallets=wallets)
    report = {"before_after": ledger_quality.summarize(annotated)}

    if args.onchain:
        candidates = []
        for r in annotated:
            if r["ledger_quality"] != ledger_quality.COUNTED_QUALITY:
                continue
            rc = _receipt(args.rpc, r["tx"])
            if not rc or rc.get("status") != "0x1" or not _pays_project(rc):
                candidates.append({"tx": r["tx"].lower(), "product_id": r.get("product_id"), "ts": r.get("ts")})
        report["exclusion_candidates"] = candidates

    json.dump(report, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
