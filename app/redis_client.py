"""One shared Redis connection for every store that needs persistence.

The quota store, the ledgers and the swarm registry all want the same Redis.
Building a client per store would open three connections to a free-tier instance
that caps them, so they share this one.

Never raises: an unreachable Redis leaves every caller on its in-memory or
file-backed fallback and records `fallback_reason` for /doctor to fail on. A
storefront that still serves 402s with degraded persistence beats one that is
down — but the degraded state must be loud, because the failure mode is silent
data loss on the next restart.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

log = logging.getLogger("x402")

# Set when REDIS_URL was configured but the connection could not be made.
fallback_reason: str | None = None


def build_client() -> Any | None:
    """Connect and PING, or return None. Call once at import; see `client`."""
    global fallback_reason

    if not settings.redis_url:
        return None
    try:
        import redis

        conn = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        conn.ping()
    except Exception as exc:  # noqa: BLE001 — any failure means fallback
        fallback_reason = f"{type(exc).__name__}: {exc}"
        log.error(
            "REDIS_URL is set but Redis is unreachable (%s) — persistent stores "
            "are falling back to memory/files. On a host without a disk that "
            "means settled sales and listings are lost on the next restart.",
            fallback_reason,
        )
        return None
    return conn


client: Any | None = build_client()
