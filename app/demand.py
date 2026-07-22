"""Count the 402 challenges each resource serves — the top of the sales funnel.

Settlements were the only thing being recorded, which makes "nobody has ever
seen this listing" and "forty agents priced it and walked away" look identical
from the outside. Those imply opposite next moves: the first is a discovery
problem, the second is a price or product problem.

Counting challenges gives the look-to-pay ratio per resource. Keys match the
`product_id` used in the revenue ledger so the two join without translation.

Follows the ops_events convention: recording must never raise into a request.
A counter is not worth failing a sale over.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger("x402")

CHALLENGE_KEY = "demand:402"
LAST_SEEN_KEY = "demand:402:last"

# Used when Redis is absent. Lost on restart, exactly like the in-memory quota
# store — on a diskless host without REDIS_URL nothing here survives anyway.
_memory: Counter[str] = Counter()
_memory_last: dict[str, str] = {}


def _client() -> Any | None:
    from app import redis_client

    return redis_client.client


def record_challenge(resource_key: str) -> None:
    """Note that `resource_key` served a 402. Never raises."""
    if not resource_key:
        return
    stamp = datetime.now(UTC).isoformat()
    try:
        client = _client()
        if client is None:
            _memory[resource_key] += 1
            _memory_last[resource_key] = stamp
            return
        pipe = client.pipeline()
        pipe.hincrby(CHALLENGE_KEY, resource_key, 1)
        pipe.hset(LAST_SEEN_KEY, resource_key, stamp)
        pipe.execute()
    except Exception:  # noqa: BLE001 — a counter must never break a sale
        log.warning("demand: failed to record a challenge for %s", resource_key)


def challenges() -> dict[str, int]:
    """Challenges served per resource key."""
    try:
        client = _client()
        if client is None:
            return dict(_memory)
        raw = client.hgetall(CHALLENGE_KEY) or {}
        return {k: int(v) for k, v in raw.items()}
    except Exception:  # noqa: BLE001
        log.warning("demand: failed to read challenge counts")
        return {}


def last_seen() -> dict[str, str]:
    try:
        client = _client()
        if client is None:
            return dict(_memory_last)
        return dict(client.hgetall(LAST_SEEN_KEY) or {})
    except Exception:  # noqa: BLE001
        return {}


def build_report() -> dict[str, Any]:
    """Per-resource funnel: challenges served, sales settled, conversion.

    `paid` counts settled revenue rows, so a resource nobody has bought reads
    0 rather than being absent. Conversion is None until at least one challenge
    has been served — a ratio over zero views says nothing.
    """
    from app.ledger_io import read_ledger_rows

    served = challenges()
    seen = last_seen()

    paid: Counter[str] = Counter()
    revenue: Counter[str] = Counter()
    for row in read_ledger_rows("revenue", limit=None):
        if not row.get("settled", True):
            continue
        key = str(row.get("product_id") or "unknown")
        paid[key] += 1
        revenue[key] += float(row.get("amount_usdc") or 0.0)

    rows = []
    for key in sorted(set(served) | set(paid)):
        views = served.get(key, 0)
        sales = paid.get(key, 0)
        rows.append(
            {
                "resource": key,
                "challenges_served": views,
                "sales_settled": sales,
                "revenue_usdc": round(revenue.get(key, 0.0), 6),
                "conversion": round(sales / views, 4) if views else None,
                "last_challenge_at": seen.get(key),
            }
        )
    rows.sort(key=lambda r: r["challenges_served"], reverse=True)

    total_views = sum(served.values())
    total_sales = sum(paid.values())
    return {
        "resources": rows,
        "total_challenges_served": total_views,
        "total_sales_settled": total_sales,
        "overall_conversion": (
            round(total_sales / total_views, 4) if total_views else None
        ),
        "note": (
            "challenges_served counts 402s handed out, i.e. agents that found "
            "the resource and read its price. A high count with no sales is a "
            "price/product signal; a zero count is a discovery signal."
        ),
    }
