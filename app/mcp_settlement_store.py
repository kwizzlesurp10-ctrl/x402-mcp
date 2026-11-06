"""Durable MCP commerce settlement: cross-worker coordination via Redis.

Semantics:
- **REDIS_URL unset:** in-process deduplication only (single worker / dev). No silent
  cross-worker guarantees.
- **REDIS_URL set:** a healthy Redis client is **required** for MCP commerce
  verify+settle (`fail closed` if unreachable). Quota store may still fall back
  separately per ``commerce.build_quota_store`` — MCP settlement is stricter.

Locking uses a random token; release only deletes the key when the value matches
(fenced token). Cache entries include a challenge fingerprint so the same payment
payload cannot authorize a different server-issued challenge.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import uuid
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_RESULT_PREFIX = "mcp_settle:result:"
_ATTEMPT_PREFIX = "mcp_settle:attempt:"
_LOCK_PREFIX = "mcp_settle:lock:"

_DEFAULT_LOCK_TTL = 120
_DEFAULT_RESULT_TTL = 86400
_DEFAULT_ATTEMPT_TTL = 86400
_DEFAULT_POLL_ATTEMPTS = 120
_DEFAULT_POLL_INTERVAL_S = 0.05

_UNLOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
"""


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
        logger.warning(
            "MCP settlement Redis unreachable (%s)",
            type(exc).__name__,
            exc_info=False,
        )
        return None


_CLIENT: Any | None = _client()


def refresh_client() -> Any | None:
    """Reconnect (e.g. after REDIS_URL change in tests)."""
    global _CLIENT
    _CLIENT = _client()
    return _CLIENT


def challenge_fingerprint(header: str) -> str:
    return hashlib.sha256(header.encode("utf-8")).hexdigest()


def composite_cache_key(payload_hash: str, payment_required_header: str) -> str:
    return f"{payload_hash}:{challenge_fingerprint(payment_required_header)}"


def redis_required_for_mcp_commerce() -> bool:
    return bool(settings.redis_url)


def mcp_commerce_redis_ready() -> bool:
    """True when MCP commerce may use Redis (strict path)."""
    return settings.mcp_commerce_redis_strict and _CLIENT is not None


def _result_key(composite: str) -> str:
    return _RESULT_PREFIX + composite


def _attempt_key(composite: str) -> str:
    return _ATTEMPT_PREFIX + composite


def _lock_key(composite: str) -> str:
    return _LOCK_PREFIX + composite


def get_cached_settlement(
    composite: str, *, expected_challenge_fp: str
) -> dict[str, Any] | None:
    if _CLIENT is None:
        return None
    try:
        raw = _CLIENT.get(_result_key(composite))
        if not raw:
            return None
        body = json.loads(raw)
        meta = body.get("_mcp_meta") or {}
        if meta.get("challenge_fp") != expected_challenge_fp:
            return None
        return body
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP settlement cache read failed (%s)", type(exc).__name__)
        return None


async def get_cached_settlement_async(
    composite: str, *, expected_challenge_fp: str
) -> dict[str, Any] | None:
    return await asyncio.to_thread(
        get_cached_settlement, composite, expected_challenge_fp=expected_challenge_fp
    )


def try_cache_settlement(
    composite: str,
    result: dict[str, Any],
    *,
    challenge_fp: str,
    ttl_seconds: int = _DEFAULT_RESULT_TTL,
) -> bool:
    if _CLIENT is None:
        return False
    try:
        out = dict(result)
        out["_mcp_meta"] = {"challenge_fp": challenge_fp, "v": 1}
        payload = json.dumps(out, separators=(",", ":"), sort_keys=True)
        return bool(_CLIENT.set(_result_key(composite), payload, nx=True, ex=ttl_seconds))
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP settlement cache write failed (%s)", type(exc).__name__)
        return False


async def try_cache_settlement_async(
    composite: str,
    result: dict[str, Any],
    *,
    challenge_fp: str,
    ttl_seconds: int = _DEFAULT_RESULT_TTL,
) -> bool:
    return await asyncio.to_thread(
        try_cache_settlement,
        composite,
        result,
        challenge_fp=challenge_fp,
        ttl_seconds=ttl_seconds,
    )


def get_attempt_state(composite: str) -> dict[str, Any] | None:
    if _CLIENT is None:
        return None
    try:
        raw = _CLIENT.get(_attempt_key(composite))
        if not raw:
            return None
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP attempt read failed (%s)", type(exc).__name__)
        return None


async def get_attempt_state_async(composite: str) -> dict[str, Any] | None:
    return await asyncio.to_thread(get_attempt_state, composite)


def set_attempt_state(
    composite: str, state: dict[str, Any], *, ttl_seconds: int = _DEFAULT_ATTEMPT_TTL
) -> None:
    if _CLIENT is None:
        return
    try:
        _CLIENT.set(
            _attempt_key(composite),
            json.dumps(state, separators=(",", ":"), sort_keys=True),
            ex=ttl_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP attempt write failed (%s)", type(exc).__name__)


async def set_attempt_state_async(
    composite: str, state: dict[str, Any], *, ttl_seconds: int = _DEFAULT_ATTEMPT_TTL
) -> None:
    await asyncio.to_thread(set_attempt_state, composite, state, ttl_seconds=ttl_seconds)


def acquire_settlement_lock(
    composite: str, *, ttl_seconds: int = _DEFAULT_LOCK_TTL
) -> tuple[bool, str | None, bool]:
    """Acquire NX lock.

    Returns (acquired, token, redis_error). ``redis_error`` is True when the
    lock could not be taken due to a missing client or Redis I/O failure
    (caller must fail closed for strict MCP commerce). When ``acquired`` is
    False and ``redis_error`` is False, another worker holds the lock.
    """
    if _CLIENT is None:
        return False, None, bool(settings.redis_url)
    token = uuid.uuid4().hex + secrets.token_hex(8)
    try:
        ok = bool(
            _CLIENT.set(_lock_key(composite), token, nx=True, ex=ttl_seconds)
        )
        return ok, token if ok else None, False
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP settlement lock acquire failed (%s)", type(exc).__name__)
        return False, None, True


async def acquire_settlement_lock_async(
    composite: str, *, ttl_seconds: int = _DEFAULT_LOCK_TTL
) -> tuple[bool, str | None, bool]:
    return await asyncio.to_thread(
        acquire_settlement_lock, composite, ttl_seconds=ttl_seconds
    )


def release_settlement_lock(composite: str, token: str) -> None:
    if _CLIENT is None or not token:
        return
    try:
        key = _lock_key(composite)
        _CLIENT.eval(_UNLOCK_LUA, 1, key, token)
    except Exception:  # noqa: BLE001
        try:
            cur = _CLIENT.get(_lock_key(composite))
            if cur == token:
                _CLIENT.delete(_lock_key(composite))
        except Exception:  # noqa: BLE001
            pass


async def release_settlement_lock_async(composite: str, token: str) -> None:
    await asyncio.to_thread(release_settlement_lock, composite, token)


async def wait_for_cached_settlement_async(
    composite: str,
    *,
    expected_challenge_fp: str,
    attempts: int = _DEFAULT_POLL_ATTEMPTS,
    interval_s: float = _DEFAULT_POLL_INTERVAL_S,
) -> dict[str, Any] | None:
    for _ in range(attempts):
        got = await get_cached_settlement_async(
            composite, expected_challenge_fp=expected_challenge_fp
        )
        if got is not None:
            return got
        att = await get_attempt_state_async(composite)
        if att and att.get("status") == "ambiguous_settlement":
            return None
        await asyncio.sleep(interval_s)
    return None


def clear_mcp_settlement_redis_test() -> None:
    """Test helper: flush MCP settlement keys."""
    if _CLIENT is None:
        return
    try:
        for pattern in (_RESULT_PREFIX + "*", _ATTEMPT_PREFIX + "*", _LOCK_PREFIX + "*"):
            for key in _CLIENT.scan_iter(match=pattern, count=64):
                _CLIENT.delete(key)
    except Exception:  # noqa: BLE001
        pass


def bind_settlement_client_for_test(client: Any | None) -> None:
    global _CLIENT
    _CLIENT = client
