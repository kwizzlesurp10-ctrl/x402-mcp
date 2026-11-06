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

import copy
import json
import logging
from typing import Any

from app.config import settings

log = logging.getLogger("x402")

_MEM: dict[str, dict[str, Any]] = {}

_KEY_PREFIX = "a2a:task:"

# Monotonic revision for optimistic concurrency (Redis durable mode).
TASK_REV_KEY = "_a2a_rev"


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
    drop: set[str] = {"binding"}
    dig = record.get("capability_digest")
    if isinstance(dig, str) and len(dig) == 64:
        # Digest proves ownership; do not store the raw token in Redis.
        drop.add("capability_token")
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


def _dump_sorted(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _mem_put(task_id: str, record: dict[str, Any]) -> bool:
    prev = _MEM.get(task_id)
    rec = copy.deepcopy(record)
    next_rev = 1
    if isinstance(prev, dict) and isinstance(prev.get(TASK_REV_KEY), int):
        next_rev = int(prev[TASK_REV_KEY]) + 1
    rec[TASK_REV_KEY] = next_rev
    _MEM[task_id] = rec
    return True


def put_task(task_id: str, record: dict[str, Any]) -> bool:
    """Persist task. When strict durable mode is on, Redis failure returns False.

    Redis path uses WATCH/MULTI so concurrent writers cannot clobber each other
    without retry; on persistent conflict the call returns False in strict mode.
    """
    r = _redis()
    if not durable_enabled() or r is None:
        return _mem_put(task_id, record)

    key = _key(task_id)
    payload_base = _json_safe(record)
    watch_retries = 32

    try:
        import redis as redis_mod

        WatchError = getattr(redis_mod, "WatchError", Exception)
    except Exception:  # noqa: BLE001
        WatchError = Exception

    for attempt in range(watch_retries):
        pipe = r.pipeline()
        try:
            pipe.watch(key)
            raw_existing = pipe.get(key)
            cur_rev: int | None = None
            if raw_existing:
                try:
                    cur_doc = json.loads(raw_existing)
                    cr = cur_doc.get(TASK_REV_KEY)
                    cur_rev = int(cr) if isinstance(cr, int) else None
                except json.JSONDecodeError:
                    cur_rev = None

            expected = record.get(TASK_REV_KEY)
            if raw_existing:
                effective_cur = cur_rev if cur_rev is not None else 0
                if not isinstance(expected, int) or expected != effective_cur:
                    pipe.unwatch()
                    if settings.a2a_task_store_redis_strict:
                        return False
                    return _mem_put(task_id, record)

            next_rev = (cur_rev + 1) if cur_rev is not None else 1

            payload = dict(payload_base)
            payload[TASK_REV_KEY] = next_rev

            pipe.multi()
            pipe.set(key, _dump_sorted(payload), ex=settings.a2a_task_ttl_seconds)
            pipe.execute()
            record[TASK_REV_KEY] = payload[TASK_REV_KEY]
            return True
        except WatchError:
            continue
        except Exception as exc:  # noqa: BLE001
            log.warning("a2a task redis write failed (%s)", type(exc).__name__)
            try:
                pipe.unwatch()
            except Exception:  # noqa: BLE001
                pass
            if settings.a2a_task_store_redis_strict:
                return False
            return _mem_put(task_id, record)
        finally:
            try:
                pipe.reset()
            except Exception:  # noqa: BLE001
                pass

    log.warning("a2a task redis CAS exceeded retries for %s", task_id)
    if settings.a2a_task_store_redis_strict:
        return False
    return _mem_put(task_id, record)


def get_task(task_id: str) -> dict[str, Any] | None:
    r = _redis()
    if durable_enabled() and r is not None:
        try:
            raw = r.get(_key(task_id))
        except Exception as exc:  # noqa: BLE001
            log.warning("a2a task redis read failed (%s)", type(exc).__name__)
            if settings.a2a_task_store_redis_strict:
                return None
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
