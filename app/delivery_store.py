"""Durable per-settlement delivery records (request input + response body).

Rows join to ``ledger:revenue`` on ``tx``. Stored under ``ledger:delivery:*`` in
Redis when configured, else under ``ledger/delivery/`` on disk (local dev).
Never raises into a paid response path.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("x402")

MAX_BODY_BYTES = 64 * 1024
MAX_RECORDS = 50_000
INDEX_KEY = "ledger:delivery:index"
RECORD_PREFIX = "ledger:delivery:tx:"

_pending_delivery_body: ContextVar[Any] = ContextVar("pending_delivery_body", default=None)


def stash_pending_delivery_body(body: Any) -> None:
    """Hold the handler/tool result until the post-settlement hook runs (MCP pilot)."""
    _pending_delivery_body.set(body)


def take_pending_delivery_body() -> Any:
    val = _pending_delivery_body.get(None)
    _pending_delivery_body.set(None)
    return val


def delivery_ref_for_tx(tx: str) -> str:
    return f"{RECORD_PREFIX}{_normalize_tx(tx)}"


def _normalize_tx(tx: str) -> str:
    return tx.strip().lower()


def _prepare_body(body: Any) -> tuple[Any, bool, str, int]:
    """Serialize, cap size, return (stored, truncated, sha256_hex, byte_len)."""
    if isinstance(body, (bytes, bytearray)):
        raw = bytes(body)
    else:
        try:
            raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            raw = json.dumps(
                {"_non_json": repr(body)[:2000]}, separators=(",", ":")
            ).encode("utf-8")

    truncated = False
    if len(raw) > MAX_BODY_BYTES:
        raw = raw[:MAX_BODY_BYTES]
        truncated = True

    sha = hashlib.sha256(raw).hexdigest()
    try:
        stored: Any = json.loads(raw)
    except json.JSONDecodeError:
        stored = raw.decode("utf-8", errors="replace")
    return stored, truncated, sha, len(raw)


def _ledger_delivery_dir() -> Path:
    from app import ledger_io

    path = ledger_io.LEDGER / "delivery"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file_index_path() -> Path:
    return _ledger_delivery_dir() / "index.json"


def _trim_file_index(index: list[str]) -> list[str]:
    if len(index) <= MAX_RECORDS:
        return index
    drop = index[MAX_RECORDS:]
    for tx in drop:
        p = _ledger_delivery_dir() / f"{_normalize_tx(tx)}.json"
        with contextlib.suppress(OSError):
            p.unlink(missing_ok=True)
    return index[:MAX_RECORDS]


def _write_file_record(record: dict[str, Any]) -> None:
    tx = record["tx"]
    path = _ledger_delivery_dir() / f"{_normalize_tx(tx)}.json"
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    idx_path = _file_index_path()
    index: list[str] = []
    if idx_path.exists():
        try:
            index = json.loads(idx_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            index = []
    tx_norm = _normalize_tx(tx)
    index = [t for t in index if t != tx_norm]
    index.insert(0, tx_norm)
    index = _trim_file_index(index)
    idx_path.write_text(json.dumps(index), encoding="utf-8")


def _read_file_record(tx: str) -> dict[str, Any] | None:
    path = _ledger_delivery_dir() / f"{_normalize_tx(tx)}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _list_file_records(*, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    idx_path = _file_index_path()
    if not idx_path.exists():
        return [], 0
    try:
        index: list[str] = json.loads(idx_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], 0
    total = len(index)
    slice_txs = index[offset : offset + limit]
    rows: list[dict[str, Any]] = []
    for tx in slice_txs:
        rec = _read_file_record(tx)
        if rec:
            rows.append(rec)
    return rows, total


def try_record_delivery(
    *,
    tx: str | None,
    route: str,
    product_id: str | None = None,
    amount_usdc: float | None = None,
    payer: str | None = None,
    request_input: Any,
    response_body: Any,
    ts: str | None = None,
) -> str | None:
    """Persist a delivery row. Returns ``delivery_ref`` or None. Never raises."""
    if not tx or not str(tx).strip():
        return None
    tx_norm = _normalize_tx(str(tx))
    try:
        stored_body, truncated, sha, nbytes = _prepare_body(response_body)
        now = ts or datetime.now(UTC).isoformat()
        atomic = int(round(amount_usdc * 1_000_000)) if amount_usdc is not None else None
        record: dict[str, Any] = {
            "tx": tx_norm,
            "ts": now,
            "route": route,
            "product_id": product_id or route,
            "amount_usdc": round(amount_usdc, 6) if amount_usdc is not None else None,
            "amount_usdc_atomic": atomic,
            "payer": payer.lower() if isinstance(payer, str) and payer else None,
            "request_input": request_input,
            "response_body": stored_body,
            "response_truncated": truncated,
            "response_sha256": sha,
            "response_bytes": nbytes,
        }
        from app import redis_client

        client = redis_client.client
        if client is None:
            _write_file_record(record)
            return delivery_ref_for_tx(tx_norm)

        key = f"{RECORD_PREFIX}{tx_norm}"
        score_ms = int(time.time() * 1000)
        pipe = client.pipeline()
        pipe.set(key, json.dumps(record, ensure_ascii=False))
        pipe.zadd(INDEX_KEY, {tx_norm: score_ms})
        pipe.execute()

        count = int(client.zcard(INDEX_KEY))
        if count > MAX_RECORDS:
            trim_count = count - MAX_RECORDS
            dropped = client.zrange(INDEX_KEY, 0, trim_count - 1)
            if dropped:
                trim_pipe = client.pipeline()
                for dropped_tx in dropped:
                    trim_pipe.delete(f"{RECORD_PREFIX}{_normalize_tx(str(dropped_tx))}")
                trim_pipe.zremrangebyrank(INDEX_KEY, 0, trim_count - 1)
                trim_pipe.execute()

        return delivery_ref_for_tx(tx_norm)
    except Exception:
        log.warning("delivery record write failed tx=%s route=%s", tx, route, exc_info=True)
        return None


def get_delivery(tx: str) -> dict[str, Any] | None:
    from app import redis_client

    client = redis_client.client
    if client is None:
        return _read_file_record(tx)
    raw = client.get(f"{RECORD_PREFIX}{_normalize_tx(tx)}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def list_deliveries(*, offset: int = 0, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    from app import redis_client

    client = redis_client.client
    if client is None:
        items, total = _list_file_records(offset=offset, limit=limit)
        return {"items": items, "offset": offset, "limit": limit, "total": total}

    total = int(client.zcard(INDEX_KEY))
    txs = client.zrevrange(INDEX_KEY, offset, offset + limit - 1)
    items: list[dict[str, Any]] = []
    for tx in txs:
        rec = get_delivery(tx)
        if rec:
            items.append(rec)
    return {"items": items, "offset": offset, "limit": limit, "total": total}