"""Read agent-ops ledger jsonl files for mission-control dashboard."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "ledger"


def read_ledger_rows(name: str, *, limit: int | None = 1000) -> list[dict]:
    """Read the spend or revenue ledger; newest first.

    `limit` caps the number of rows for display; pass `limit=None` to read the
    whole ledger (used for spend/revenue aggregation, which must not truncate).

    Reads Redis when REDIS_URL is configured and reachable, otherwise the jsonl
    files. The store is resolved per call so tests can swap it out.
    """
    if name not in ("spend", "revenue"):
        raise ValueError("ledger name must be spend or revenue")

    from app import ledger_store as store_module

    if store_module.ledger_store is not None:
        return store_module.ledger_store.read(name, limit)

    path = LEDGER / f"{name}.jsonl"
    if not path.exists():
        return []

    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    rows.reverse()
    return rows if limit is None else rows[:limit]


def operator_wallet_set() -> set[str]:
    """Lowercased operator wallets from config, empty when unconfigured."""
    from app.config import settings

    return {w.strip().lower() for w in settings.operator_wallets.split(",") if w.strip()}


def classify_operator_settle(
    row: dict, operator_wallets: set[str] | None = None
) -> bool | None:
    """Is this revenue row the operator paying themselves?

    True when the row's `payer` matches a configured operator wallet
    (cataloging/re-indexing, not a customer), False when it's a different
    wallet (a real external sale), and None when `payer` is missing or no
    operator wallets are configured — rows written before the field existed,
    or a settlement whose facilitator didn't report one.

    Treat None as "unknown", never as "external": most of this project's
    revenue history is self-settled, and the honest default is not to
    overclaim a sale. Counting operator settles as sales is what reported
    mn-property-check at 4% conversion when its confirmed external sales
    were zero.
    """
    wallets = operator_wallet_set() if operator_wallets is None else operator_wallets
    payer = row.get("payer")
    if not payer or not wallets:
        return None
    try:
        return str(payer).lower() in wallets
    except Exception:  # a malformed payer is unknown, never external
        return None