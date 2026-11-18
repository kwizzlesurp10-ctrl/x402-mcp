"""Entry point for the sale-watch GitHub Action (stdlib + gh only)."""

from __future__ import annotations

import os
import sys
from datetime import timedelta

from alerts import Alerter, event_key
from sale_watch_base import (
    RpcInfrastructureError,
    fetch_transfer_logs,
    latest_block_number,
    rpc_call,
)
from sale_watch_detect import (
    StrangerPayment,
    external_sales_from_ledger_rows,
    fetch_ledger_revenue,
    merge_stranger_payments,
    normalize_wallet,
    strangers_from_transfer_logs,
)


def _wallet_set(raw: str) -> set[str]:
    return {normalize_wallet(w) for w in raw.split(",") if w.strip()}


def _chain_strangers(
    usdc: str, pay_to: str, our_wallets: set[str]
) -> tuple[list[StrangerPayment], bool]:
    try:
        latest = latest_block_number(rpc_call)
        start = max(0, latest - 3600)
        logs = fetch_transfer_logs(
            rpc_call,
            usdc=usdc,
            pay_to=pay_to,
            start_block=start,
            end_block=latest,
        )
    except RpcInfrastructureError as exc:
        print(f"::warning::Base RPC unavailable; chain scan skipped: {exc}")
        return [], False

    strangers = strangers_from_transfer_logs(logs, our_wallets)
    print(
        f"chain: scanned {latest - start} blocks; "
        f"{len(logs)} payments in, {len(strangers)} from strangers"
    )
    return strangers, True


def _ledger_lookback() -> timedelta:
    hours = float(os.environ.get("LEDGER_LOOKBACK_HOURS", "12"))
    return timedelta(hours=max(0.0, hours))


def _ledger_strangers(our_wallets: set[str]) -> tuple[list[StrangerPayment], bool]:
    base_url = os.environ.get("STOREFRONT_URL", "https://x402-mcp.onrender.com")
    try:
        rows = fetch_ledger_revenue(base_url)
    except RuntimeError as exc:
        print(f"::warning::{exc}")
        return [], False

    lookback = _ledger_lookback()
    strangers = external_sales_from_ledger_rows(
        rows, our_wallets, lookback=lookback if lookback.total_seconds() > 0 else None
    )
    print(f"ledger: {len(rows)} revenue rows, {len(strangers)} external settled sales")
    return strangers, True


def main() -> int:
    pay_to = os.environ["PAY_TO"].lower()
    usdc = os.environ["USDC"]
    our_wallets = _wallet_set(os.environ["OUR_WALLETS"])
    repo = os.environ["GH_REPO"]

    chain, chain_ok = _chain_strangers(usdc, pay_to, our_wallets)
    ledger, ledger_ok = _ledger_strangers(our_wallets)
    if not chain_ok and not ledger_ok:
        print("no detection source succeeded; exiting without alerts")
        return 0

    strangers = merge_stranger_payments(chain, ledger)
    print(f"merged {len(strangers)} unique external sale(s)")

    max_per_run = int(os.environ.get("MAX_SALE_ALERTS_PER_RUN", "15"))
    alerter = Alerter(repo, "sale", max_alerts_per_run=max_per_run)

    for sale in strangers:
        product_line = (
            f"- **Product:** `{sale.product_id}`\n" if sale.product_id else ""
        )
        block_line = (
            f"- **Block:** {sale.block}\n" if sale.block is not None else ""
        )
        alerter.alert(
            event_key("sale", sale.tx),
            f"\U0001F4B0 External sale: ${sale.amount_usdc:.4f} USDC from {sale.payer[:10]}…",
            f"A wallet that is not ours paid the storefront "
            f"(source: {sale.source}).\n\n"
            f"- **Amount:** ${sale.amount_usdc:.6f} USDC\n"
            f"- **From:** `{sale.payer}`\n"
            f"- **To (pay_to):** `{pay_to}`\n"
            f"{product_line}"
            f"- **Tx:** https://basescan.org/tx/{sale.tx}\n"
            f"{block_line}\n"
            f"Cross-check /ledger/revenue and /demand for product fit. "
            f"Close this issue once acknowledged.",
        )

    print(alerter.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())