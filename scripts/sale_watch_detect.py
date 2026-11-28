"""Detection helpers for sale-watch — chain logs plus storefront ledger."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class StrangerPayment:
    payer: str
    amount_usdc: float
    tx: str
    block: int | None
    product_id: str | None
    source: str


def normalize_wallet(addr: str) -> str:
    return (addr or "").strip().lower()


def strangers_from_transfer_logs(
    logs: list[dict[str, Any]],
    our_wallets: set[str],
) -> list[StrangerPayment]:
    strangers: list[StrangerPayment] = []
    for lg in logs:
        frm = "0x" + lg["topics"][1][-40:]
        if normalize_wallet(frm) in our_wallets:
            continue
        amt = int(lg["data"], 16) / 1e6
        tx = lg["transactionHash"]
        if not tx.startswith("0x"):
            tx = "0x" + tx
        block = int(lg["blockNumber"], 16) if lg.get("blockNumber") else None
        strangers.append(
            StrangerPayment(
                payer=frm,
                amount_usdc=amt,
                tx=tx,
                block=block,
                product_id=None,
                source="chain",
            )
        )
    return strangers


def _decode_revenue_rows(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("entries", "lines", "rows"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [row for row in nested if isinstance(row, dict)]
    return []


def fetch_ledger_revenue(base_url: str, *, timeout: float = 45.0) -> list[dict[str, Any]]:
    url = base_url.rstrip("/") + "/ledger/revenue"
    request = urllib.request.Request(
        url,
        headers={"accept": "application/json", "user-agent": "x402-sale-watch/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _decode_revenue_rows(json.loads(response.read()))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"ledger fetch failed: {exc}") from exc


def _parse_ts(raw: object) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def external_sales_from_ledger_rows(
    rows: list[dict[str, Any]],
    our_wallets: set[str],
    *,
    lookback: timedelta | None = None,
) -> list[StrangerPayment]:
    cutoff = (
        datetime.now(timezone.utc) - lookback if lookback is not None else None
    )
    sales: list[StrangerPayment] = []
    for row in rows:
        if not row.get("settled"):
            continue
        if cutoff is not None:
            ts = _parse_ts(row.get("ts"))
            if ts is None or ts < cutoff:
                continue
        if row.get("is_operator_settle") is True:
            continue
        payer = normalize_wallet(str(row.get("payer") or ""))
        if not payer or payer in our_wallets:
            continue
        tx = str(row.get("tx") or "").strip()
        if not tx:
            continue
        if not tx.startswith("0x"):
            tx = "0x" + tx
        try:
            amount = float(row.get("amount_usdc") or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        product = row.get("product_id") or row.get("agent_id")
        sales.append(
            StrangerPayment(
                payer=row.get("payer") or payer,
                amount_usdc=amount,
                tx=tx,
                block=None,
                product_id=str(product) if product else None,
                source="ledger",
            )
        )
    return sales


def merge_stranger_payments(
    chain: list[StrangerPayment],
    ledger: list[StrangerPayment],
) -> list[StrangerPayment]:
    merged: dict[str, StrangerPayment] = {}
    for item in chain:
        merged[item.tx.lower()] = item
    for item in ledger:
        key = item.tx.lower()
        if key in merged:
            existing = merged[key]
            merged[key] = StrangerPayment(
                payer=item.payer,
                amount_usdc=item.amount_usdc,
                tx=item.tx,
                block=existing.block if existing.block is not None else item.block,
                product_id=item.product_id or existing.product_id,
                source="chain+ledger",
            )
        else:
            merged[key] = item
    return sorted(merged.values(), key=lambda p: p.tx)