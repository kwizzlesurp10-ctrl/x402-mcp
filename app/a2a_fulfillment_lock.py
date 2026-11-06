"""Single-flight guard for A2A paid fulfillment (multi-worker when Redis up)."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("x402")

_KEY_PREFIX = "a2a:fulfill:lock:"
_DEFAULT_TTL = 900


def _redis() -> Any | None:
    from app import redis_client

    return redis_client.client


def try_acquire(task_id: str, *, ttl_seconds: int = _DEFAULT_TTL) -> bool:
    """Return True if this worker may run fulfillment; False if another holds the lock."""
    r = _redis()
    if r is None:
        return True
    try:
        return bool(r.set(_KEY_PREFIX + task_id, "1", nx=True, ex=ttl_seconds))
    except Exception as exc:  # noqa: BLE001
        log.warning("a2a fulfillment lock acquire failed (%s)", type(exc).__name__)
        return True


def release(task_id: str) -> None:
    r = _redis()
    if r is None:
        return
    try:
        r.delete(_KEY_PREFIX + task_id)
    except Exception:  # noqa: BLE001
        pass


def clear_for_test() -> None:
    r = _redis()
    if r is None:
        return
    try:
        for k in r.scan_iter(match=_KEY_PREFIX + "*", count=64):
            r.delete(k)
    except Exception:  # noqa: BLE001
        pass
