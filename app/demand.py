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
# When counting started. Sales older than this predate the instrumentation, and
# dividing them by views collected since would report conversions above 100%.
SINCE_KEY = "demand:402:since"

# Used when Redis is absent. Lost on restart, exactly like the in-memory quota
# store — on a diskless host without REDIS_URL nothing here survives anyway.
_memory: Counter[str] = Counter()
_memory_last: dict[str, str] = {}
_memory_since: str | None = None


def _client() -> Any | None:
    from app import redis_client

    return redis_client.client


def record_challenge(resource_key: str) -> None:
    """Note that `resource_key` served a 402. Never raises."""
    if not resource_key:
        return
    global _memory_since
    stamp = datetime.now(UTC).isoformat()
    try:
        client = _client()
        if client is None:
            if _memory_since is None:
                _memory_since = stamp
            _memory[resource_key] += 1
            _memory_last[resource_key] = stamp
            return
        pipe = client.pipeline()
        pipe.hincrby(CHALLENGE_KEY, resource_key, 1)
        pipe.hset(LAST_SEEN_KEY, resource_key, stamp)
        pipe.set(SINCE_KEY, stamp, nx=True)  # first write wins
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


def _parse_ts(value: str) -> datetime | None:
    """Parse an ISO-8601 stamp, tolerating a missing offset. None if unusable.

    Compared as datetimes rather than strings so a row written with a different
    UTC offset still sorts correctly against the counting-since marker.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def counting_since() -> str | None:
    """When challenge counting began, or None if it never has."""
    try:
        client = _client()
        if client is None:
            return _memory_since
        return client.get(SINCE_KEY)
    except Exception:  # noqa: BLE001
        return None


def build_report() -> dict[str, Any]:
    """Per-resource funnel: challenges served, sales settled, conversion.

    `paid` counts settled revenue rows, so a resource nobody has bought reads
    0 rather than being absent. Conversion is None until at least one challenge
    has been served — a ratio over zero views says nothing.
    """
    from app.ledger_io import read_ledger_rows

    served = challenges()
    seen = last_seen()
    since = counting_since()

    since_dt = _parse_ts(since) if since else None

    paid: Counter[str] = Counter()
    revenue: Counter[str] = Counter()
    counted: Counter[str] = Counter()  # sales inside the measured window only
    for row in read_ledger_rows("revenue", limit=None):
        if not row.get("settled", True):
            continue
        key = str(row.get("product_id") or "unknown")
        paid[key] += 1
        revenue[key] += float(row.get("amount_usdc") or 0.0)
        row_dt = _parse_ts(str(row.get("ts") or ""))
        if since_dt and row_dt and row_dt >= since_dt:
            counted[key] += 1

    rows = []
    for key in sorted(set(served) | set(paid)):
        views = served.get(key, 0)
        sales = paid.get(key, 0)
        rows.append(
            {
                "resource": key,
                "challenges_served": views,
                "sales_settled": sales,
                "sales_in_window": counted.get(key, 0),
                "revenue_usdc": round(revenue.get(key, 0.0), 6),
                # Only sales inside the measured window, so this can never
                # exceed 1.0 by comparing old sales against new views.
                "conversion": (
                    round(counted.get(key, 0) / views, 4) if views else None
                ),
                "last_challenge_at": seen.get(key),
            }
        )
    rows.sort(key=lambda r: r["challenges_served"], reverse=True)

    total_views = sum(served.values())
    total_sales = sum(paid.values())
    total_in_window = sum(counted.values())
    return {
        "resources": rows,
        "total_challenges_served": total_views,
        "total_sales_settled": total_sales,
        "counting_since": since,
        "total_sales_in_window": total_in_window,
        "overall_conversion": (
            round(total_in_window / total_views, 4) if total_views else None
        ),
        "note": (
            "challenges_served counts 402s handed out, i.e. agents that found "
            "the resource and read its price. A high count with no sales is a "
            "price/product signal; a zero count is a discovery signal. "
            "conversion uses only sales settled since counting_since, so it is "
            "not skewed by sales that predate the instrumentation."
        ),
    }
