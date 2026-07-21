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