"""Durable MCP commerce settlement cache (cross-worker) when Redis is available."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "mcp_settle:"
_LOCK_PREFIX = "mcp_settle_lock:"
_DEFAULT_LOCK_TTL = 90
_DEFAULT_POLL_ATTEMPTS = 60
_DEFAULT_POLL_INTERVAL = 0.05


def _client():
    if not settings.redis_url:
        return None
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP settlement Redis unavailable (%s): %s", type(exc).__name__, exc)
        return None


_CLIENT = _client()


def get_cached_settlement(cache_key: str) -> dict[str, Any] | None:
    if _CLIENT is None:
        return None
    try:
        raw = _CLIENT.get(_KEY_PREFIX + cache_key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP settlement cache read failed: %s", exc)
        return None


def try_cache_settlement(
    cache_key: str, result: dict[str, Any], *, ttl_seconds: int = 86400
) -> bool:
    """SET only if missing. Returns True if this caller wrote the cache entry."""
    if _CLIENT is None:
        return False
    try:
        payload = json.dumps(result, separators=(",", ":"), sort_keys=True)
        ok = bool(
            _CLIENT.set(
                _KEY_PREFIX + cache_key,
                payload,
                nx=True,
                ex=ttl_seconds,
            )
        )
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP settlement cache write failed: %s", exc)
        return False


def acquire_settlement_lock(cache_key: str, *, ttl_seconds: int = _DEFAULT_LOCK_TTL) -> bool:
    if _CLIENT is None:
        return True
    try:
        return bool(_CLIENT.set(_LOCK_PREFIX + cache_key, "1", nx=True, ex=ttl_seconds))
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP settlement lock acquire failed: %s", exc)
        return True


def release_settlement_lock(cache_key: str) -> None:
    if _CLIENT is None:
        return
    try:
        _CLIENT.delete(_LOCK_PREFIX + cache_key)
    except Exception:  # noqa: BLE001
        pass


def wait_for_cached_settlement(
    cache_key: str,
    *,
    attempts: int = _DEFAULT_POLL_ATTEMPTS,
    interval: float = _DEFAULT_POLL_INTERVAL,
) -> dict[str, Any] | None:
    import time as time_mod

    for _ in range(attempts):
        got = get_cached_settlement(cache_key)
        if got is not None:
            return got
        time_mod.sleep(interval)
    return None


def clear_mcp_settlement_redis_test() -> None:
    """Test helper: flush MCP settlement keys (use only in isolated tests)."""
    if _CLIENT is None:
        return
    try:
        for key in _CLIENT.scan_iter(match=_KEY_PREFIX + "*", count=64):
            _CLIENT.delete(key)
        for key in _CLIENT.scan_iter(match=_LOCK_PREFIX + "*", count=64):
            _CLIENT.delete(key)
    except Exception:  # noqa: BLE001
        pass


def bind_settlement_client_for_test(client: Any | None) -> None:
    """Test-only: inject Redis client (e.g. fakeredis); None disables Redis layer."""
    global _CLIENT
    _CLIENT = client
