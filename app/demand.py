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

# Requests carrying this header are our own — the uptime monitor, deploy smoke
# checks, anything on a timer. They are NOT demand, and counting them makes the
# metric climb forever whether or not a single buyer ever shows up.
SELF_TRAFFIC_HEADER = "x-demand-ignore"

# Per-resource tally of WHO is knocking, so "views" can be read as demand vs
# bot noise. A raw user-agent has unbounded cardinality (and can carry PII-ish
# bits), so requests are bucketed into a small fixed set of client classes. The
# question this answers: are the challenges genuine agent clients, or crawlers?
CLIENTS_KEY = "demand:402:clients"
_memory_clients: dict[str, Counter[str]] = {}

# A bounded sample of the DISTINCT raw User-Agents per resource. The client
# class tells you "payment-capable or bot"; the raw string tells you WHO — a
# named ecosystem indexer (x402scan, CDP crawler, a re-indexer) reads very
# differently from a varied set of real agent runtimes. Capped so cardinality
# stays bounded; UA strings are software identifiers, not personal data.
UA_SAMPLE_KEY = "demand:402:ua"
_UA_SAMPLE_CAP = 40
_memory_ua: dict[str, set[str]] = {}

# Ordered most-specific first; first match wins.
_CLIENT_SIGNATURES = (
    ("x402-client", ("x402", "x402httpx", "x402-fetch", "x402-axios")),
    ("coinbase-agentkit", ("agentkit", "cdp-sdk", "coinbase")),
    ("langchain-agent", ("langchain", "langgraph", "crewai", "autogpt")),
    ("python-http", ("python-httpx", "httpx", "aiohttp", "python-requests", "urllib")),
    ("node-http", ("node-fetch", "undici", "axios", "got (", "node.js")),
    ("browser", ("mozilla", "chrome", "safari", "webkit")),
    ("crawler-bot", ("bot", "crawler", "spider", "scan", "probe", "curl", "wget", "monitor")),
)


def classify_client(user_agent: str | None) -> str:
    """Bucket a User-Agent into a coarse client class. Never the raw string."""
    if not user_agent:
        return "unknown"
    ua = user_agent.lower()
    for label, needles in _CLIENT_SIGNATURES:
        if any(n in ua for n in needles):
            return label
    return "other"

# Used when Redis is absent. Lost on restart, exactly like the in-memory quota
# store — on a diskless host without REDIS_URL nothing here survives anyway.
_memory: Counter[str] = Counter()
_memory_last: dict[str, str] = {}
_memory_since: str | None = None


def _client() -> Any | None:
    from app import redis_client

    return redis_client.client


def is_self_traffic(headers: Any) -> bool:
    """True when a request is our own tooling rather than a prospective buyer."""
    try:
        return bool(headers.get(SELF_TRAFFIC_HEADER))
    except Exception:  # noqa: BLE001 — never break a request over a counter
        return False


def record_challenge(resource_key: str, user_agent: str | None = None) -> None:
    """Note that `resource_key` served a 402, and to what class of client. Never raises."""
    if not resource_key:
        return
    global _memory_since
    stamp = datetime.now(UTC).isoformat()
    client_class = classify_client(user_agent)
    try:
        client = _client()
        if client is None:
            if _memory_since is None:
                _memory_since = stamp
            _memory[resource_key] += 1
            _memory_last[resource_key] = stamp
            _memory_clients.setdefault(resource_key, Counter())[client_class] += 1
            _sample_ua(None, resource_key, user_agent)
            return
        pipe = client.pipeline()
        pipe.hincrby(CHALLENGE_KEY, resource_key, 1)
        pipe.hset(LAST_SEEN_KEY, resource_key, stamp)
        pipe.set(SINCE_KEY, stamp, nx=True)  # first write wins
        pipe.hincrby(CLIENTS_KEY, f"{resource_key}|{client_class}", 1)
        pipe.execute()
        _sample_ua(client, resource_key, user_agent)
    except Exception:  # noqa: BLE001 — a counter must never break a sale
        log.warning("demand: failed to record a challenge for %s", resource_key)


def _sample_ua(client: Any, resource_key: str, user_agent: str | None) -> None:
    """Keep up to _UA_SAMPLE_CAP distinct raw UAs per resource. Best-effort."""
    if not user_agent:
        return
    ua = user_agent[:160]
    key = f"{UA_SAMPLE_KEY}:{resource_key}"
    try:
        if client is None:
            s = _memory_ua.setdefault(resource_key, set())
            if ua in s or len(s) < _UA_SAMPLE_CAP:
                s.add(ua)
            return
        # SADD is a no-op for a dup; only grow while under the cap.
        if client.sismember(key, ua) or client.scard(key) < _UA_SAMPLE_CAP:
            client.sadd(key, ua)
    except Exception:  # noqa: BLE001
        pass


def ua_samples() -> dict[str, list[str]]:
    """Distinct raw User-Agents sampled per resource."""
    try:
        client = _client()
        if client is None:
            return {k: sorted(v) for k, v in _memory_ua.items()}
        out: dict[str, list[str]] = {}
        for res in challenges():
            members = client.smembers(f"{UA_SAMPLE_KEY}:{res}") or set()
            if members:
                out[res] = sorted(members)
        return out
    except Exception:  # noqa: BLE001
        return {}


def clients_by_resource() -> dict[str, dict[str, int]]:
    """Per-resource breakdown of client classes that hit each 402."""
    out: dict[str, dict[str, int]] = {}
    try:
        client = _client()
        if client is None:
            return {k: dict(v) for k, v in _memory_clients.items()}
        raw = client.hgetall(CLIENTS_KEY) or {}
        for field, count in raw.items():
            resource, _, cls = field.rpartition("|")
            out.setdefault(resource, {})[cls] = int(count)
    except Exception:  # noqa: BLE001
        log.warning("demand: failed to read client breakdown")
    return out


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
    clients = clients_by_resource()
    uas = ua_samples()

    # A view is only plausibly a buyer if a real client made it. Crawlers,
    # monitors, and bare browsers are not going to sign a USDC authorization.
    bot_classes = {"crawler-bot", "browser", "unknown"}

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
        by_client = clients.get(key, {})
        qualified = sum(n for cls, n in by_client.items() if cls not in bot_classes)
        rows.append(
            {
                "resource": key,
                "challenges_served": views,
                # Views from a client that could actually pay (excludes crawlers,
                # bare browsers, and un-identified traffic). This is the number
                # that means "prospective buyer", not "something hit the URL".
                "qualified_views": qualified,
                "clients": by_client,
                "sales_settled": sales,
                "sales_in_window": counted.get(key, 0),
                "user_agents": uas.get(key, []),
                "revenue_usdc": round(revenue.get(key, 0.0), 6),
                # Only sales inside the measured window, so this can never
                # exceed 1.0 by comparing old sales against new views.
                "conversion": (
                    round(counted.get(key, 0) / views, 4) if views else None
                ),
                "last_challenge_at": seen.get(key),
            }
        )
    rows.sort(key=lambda r: r["qualified_views"], reverse=True)

    total_views = sum(served.values())
    total_qualified = sum(r["qualified_views"] for r in rows)
    total_sales = sum(paid.values())
    total_in_window = sum(counted.values())
    return {
        "resources": rows,
        "total_challenges_served": total_views,
        "total_qualified_views": total_qualified,
        "total_sales_settled": total_sales,
        "counting_since": since,
        "total_sales_in_window": total_in_window,
        "overall_conversion": (
            round(total_in_window / total_views, 4) if total_views else None
        ),
        "note": (
            "challenges_served counts every 402 handed out; qualified_views "
            "excludes crawlers, bare browsers and unidentified traffic (see "
            "clients). Read qualified_views, not challenges_served, as demand: "
            "qualified with no sales is a price/product signal; zero qualified "
            "is a discovery signal even if challenges_served is high."
        ),
    }
