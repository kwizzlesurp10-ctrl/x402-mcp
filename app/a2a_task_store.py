"""Durable A2A task records (Redis when available; otherwise in-process).

When ``REDIS_URL`` is set and the shared ``redis_client`` connects, tasks are
stored under ``a2a:task:{task_id}`` with TTL ``A2A_TASK_TTL_SECONDS`` (default
7d). Capability tokens and client binding are persisted; ``SkillBinding`` is
**not** serialized — on load we rehydrate from ``skillId`` via the same registry
as runtime (`a2a_rpc._skill_bindings`). If a skill no longer exists, the task
surfaces as failed with a clear message.

This module never logs raw payment payloads or signatures.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings

log = logging.getLogger("x402")

_MEM: dict[str, dict[str, Any]] = {}

_KEY_PREFIX = "a2a:task:"


def _redis():
    from app import redis_client

    return redis_client.client


def durable_enabled() -> bool:
    return bool(settings.redis_url) and settings.a2a_task_store_redis and _redis() is not None


def mode() -> str:
    if durable_enabled():
        return "redis"
    if settings.redis_url and settings.a2a_task_store_redis:
        return "memory_redis_unavailable"
    return "memory"


def _key(task_id: str) -> str:
    return _KEY_PREFIX + task_id


def _json_safe(record: dict[str, Any]) -> dict[str, Any]:
    """Drop non-JSON and object refs; keep task JSON-serializable."""
    drop = {"binding"}
    out: dict[str, Any] = {}
    for k, v in record.items():
        if k in drop:
            continue
        try:
            json.dumps(v, default=str)
        except (TypeError, ValueError):
            continue
        out[k] = v
    out["_a2a_store_v"] = 1
    return out


def put_task(task_id: str, record: dict[str, Any]) -> None:
    payload = _json_safe(record)
    r = _redis()
    if durable_enabled() and r is not None:
        try:
            r.set(
                _key(task_id),
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
                ex=settings.a2a_task_ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("a2a task redis write failed (%s)", type(exc).__name__)
            _MEM[task_id] = dict(record)
        return
    _MEM[task_id] = dict(record)


def get_task(task_id: str) -> dict[str, Any] | None:
    r = _redis()
    if durable_enabled() and r is not None:
        try:
            raw = r.get(_key(task_id))
        except Exception as exc:  # noqa: BLE001
            log.warning("a2a task redis read failed (%s)", type(exc).__name__)
            return _MEM.get(task_id)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return _MEM.get(task_id)


def delete_task(task_id: str) -> None:
    r = _redis()
    _MEM.pop(task_id, None)
    if r is not None:
        try:
            r.delete(_key(task_id))
        except Exception:  # noqa: BLE001
            pass


def clear_for_test() -> None:
    """Test hook: wipe memory and Redis keys for this prefix."""
    global _MEM
    _MEM = {}
    r = _redis()
    if r is None:
        return
    try:
        for k in r.scan_iter(match=_KEY_PREFIX + "*", count=64):
            r.delete(k)
    except Exception:  # noqa: BLE001
        pass
