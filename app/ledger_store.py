"""Backing store for the spend/revenue ledgers.

The ledgers started as append-only jsonl under `ledger/`, which is fine on a box
with a disk. The public storefront is not one: Render's free plan restarts the
instance on its own and comes back with an empty filesystem, so the record of
every settled sale is lost while the money is still on-chain. That already
happened once (2026-07-21) and cost us the local record of two real sales.

When REDIS_URL is set the ledgers live in Redis lists instead, sharing the
instance the quota store already uses. Files stay the default so local
development and the tests keep working untouched, and a Redis that cannot be
reached falls back to files rather than taking the server down — /doctor
surfaces the degraded state.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings

log = logging.getLogger("x402")

LEDGER_NAMES = ("spend", "revenue")

# Redis trims each ledger to this many rows. Ledger rows are small (~250 bytes)
# and the aggregate endpoints read the whole list, so this bounds both memory on
# a free Redis plan and the work /swarm/revenue does per request.
MAX_ROWS = 50_000

# Set when REDIS_URL was configured but we fell back to files anyway.
fallback_reason: str | None = None


def _validate(name: str) -> str:
    if name not in LEDGER_NAMES:
        raise ValueError("ledger name must be spend or revenue")
    return name


class RedisLedgerStore:
    """Append-only ledgers in Redis lists, one list per ledger name.

    Rows are RPUSHed so list order is chronological, matching the jsonl files;
    readers reverse to newest-first exactly as the file reader does.
    """

    mode = "redis"

    def __init__(self, client: Any, key_prefix: str = "ledger") -> None:
        self._client = client
        self._prefix = key_prefix

    def _key(self, name: str) -> str:
        return f"{self._prefix}:{_validate(name)}"

    def append(self, name: str, row: dict[str, Any]) -> dict[str, Any]:
        key = self._key(name)
        pipe = self._client.pipeline()
        pipe.rpush(key, json.dumps(row))
        pipe.ltrim(key, -MAX_ROWS, -1)
        pipe.execute()
        return row

    def read(self, name: str, limit: int | None) -> list[dict[str, Any]]:
        raw = self._client.lrange(self._key(name), 0, -1)
        rows: list[dict[str, Any]] = []
        for entry in raw:
            try:
                rows.append(json.loads(entry))
            except (TypeError, json.JSONDecodeError):
                continue  # a corrupt row must not sink the whole ledger
        rows.reverse()
        return rows if limit is None else rows[:limit]

    def ping(self) -> None:
        self._client.ping()


def build_ledger_store() -> RedisLedgerStore | None:
    """Pick the ledger backend at import time; None means the jsonl files.

    Mirrors build_quota_store: REDIS_URL unset -> files, reachable -> Redis,
    unreachable -> files plus a loud log and a fallback_reason /doctor can fail
    on. Never raises, because an unreachable Redis must not stop the server from
    booting — a storefront that serves 402s with a degraded ledger is still
    better than one that is down.
    """
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
    except Exception as exc:  # noqa: BLE001 — any failure means fallback
        log.error(
            "REDIS_URL is set but Redis is unreachable (%s: %s) — the spend and "
            "revenue ledgers are falling back to FILES. On an ephemeral host "
            "that means settled sales will be lost on the next restart.",
            type(exc).__name__,
            exc,
        )
        global fallback_reason
        fallback_reason = f"{type(exc).__name__}: {exc}"
        return None
    log.info("Ledger store: Redis (settled spend/revenue survive a restart)")
    return RedisLedgerStore(client)


ledger_store: RedisLedgerStore | None = build_ledger_store()
