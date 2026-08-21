"""Append-only writer for the spend/revenue ledgers the dashboard reads.

The repo shipped only a *reader* (app.ledger_io); the swarm records cost basis
and realized revenue here so margin is derivable. Rows go to Redis when one is
configured (see app.ledger_store — required on hosts with no persistent disk),
otherwise to jsonl. File paths resolve through app.ledger_io.LEDGER at call time
so tests can redirect storage via monkeypatch.
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

    from app import ledger_store as store_module

    if store_module.ledger_store is not None:
        written = store_module.ledger_store.append(name, row)
    else:
        ledger_dir = ledger_io.LEDGER
        ledger_dir.mkdir(parents=True, exist_ok=True)
        path = ledger_dir / f"{name}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        written = row

    # Drop the 10s /ledger cache entry so the next dashboard poll sees the sale.
    # Steady-state polling still hits memory; only post-write traffic refreshes.
    try:
        from app.main import invalidate_ledger_cache

        invalidate_ledger_cache(name)
    except Exception:  # never let cache bookkeeping break a settled write
        pass
    return written


def record_spend(
    *,
    agent_id: str,
    amount_usdc: float,
    network: str,
    url: str,
    run_id: str,
    tx: str | None = None,
    settled: bool = False,
    amount_source: str | None = None,
) -> dict[str, Any]:
    """Record an upstream purchase (buy side / cost basis).

    `amount_source` says where `amount_usdc` came from, because not every
    caller can recover the exact charge:

    - ``"settlement"`` — the facilitator's own settled amount. Exact.
    - ``"authorized"`` — the amount the buyer signed for in the selected
      payment requirements. Exact absent a partial settlement.
    - ``"cap_upper_bound"`` — no real amount was recoverable and a spend *cap*
      was recorded instead. The true charge is at most this. Warden reads this
      ledger for its daily/monthly caps (app/swarm/policy.py:65-83), so an
      overstatement here wrongly refuses later purchases — flagging it beats
      silently claiming precision.
    - ``None`` — legacy/unspecified (rows written before this field existed).
    """
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "kind": "spend",
        "agent_id": agent_id,
        "network": network,
        "amount_usdc": round(amount_usdc, 6),
        "amount_usdc_atomic": _atomic(amount_usdc),
        "amount_source": amount_source,
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
    payer: str | None = None,
) -> dict[str, Any]:
    """Record a realized composite sale (sell side / revenue).

    `payer` is the buyer's wallet address from the facilitator's settle
    response (`SettleResponse.payer`) when available — it's what lets a real
    external sale be told apart from the operator settling against its own
    listing, which `agent_id` cannot do (it's a seller/product label, not a
    buyer identity).
    """
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
        "payer": payer.lower() if payer else None,
    }
    return _append("revenue", row)
