"""Append-only writer for the spend/revenue ledgers the dashboard reads.

The repo shipped only a *reader* (app.ledger_io); the swarm records cost basis
and realized revenue here so margin is derivable. Paths resolve through
app.ledger_io.LEDGER at call time so tests can redirect storage via monkeypatch.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app import ledger_io


def _atomic(amount_usdc: float) -> int:
    """USDC has 6 decimals; store the integer atomic amount the dashboard nets on."""
    return int(round(amount_usdc * 1_000_000))


def _append(name: str, row: dict[str, Any]) -> dict[str, Any]:
    if name not in ("spend", "revenue"):
        raise ValueError("ledger name must be spend or revenue")
    ledger_dir = ledger_io.LEDGER
    ledger_dir.mkdir(parents=True, exist_ok=True)
    path = ledger_dir / f"{name}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def record_spend(
    *,
    agent_id: str,
    amount_usdc: float,
    network: str,
    url: str,
    run_id: str,
    tx: str | None = None,
    settled: bool = False,
) -> dict[str, Any]:
    """Record an upstream purchase (buy side / cost basis)."""
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "kind": "spend",
        "agent_id": agent_id,
        "network": network,
        "amount_usdc": round(amount_usdc, 6),
        "amount_usdc_atomic": _atomic(amount_usdc),
        "tx": tx,
        "settled": settled,
        "url": url,
        "run_id": run_id,
    }
    return _append("spend", row)


def record_revenue(
    *,
    agent_id: str,
    amount_usdc: float,
    network: str,
    product_id: str,
    run_id: str | None = None,
    tx: str | None = None,
    settled: bool = True,
) -> dict[str, Any]:
    """Record a realized composite sale (sell side / revenue)."""
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "kind": "revenue",
        "agent_id": agent_id,
        "network": network,
        "amount_usdc": round(amount_usdc, 6),
        "amount_usdc_atomic": _atomic(amount_usdc),
        "tx": tx,
        "settled": settled,
        "product_id": product_id,
        "run_id": run_id,
    }
    return _append("revenue", row)
