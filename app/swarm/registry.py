"""Registry of swarm runs and listed composite products.

Runs and source scores mirror the app's other stores (quota_store, ops_events)
— ephemeral, capped, lost on restart. Listed products and the settlement replay
guard persist: to Redis when one is configured (the only option that holds on a
host with no disk, where a restart would otherwise reset a sold product's
revenue to zero), otherwise to a JSON file (`SWARM_PRODUCTS_FILE`, default
`ledger/products.json`, git-ignored; empty string disables it).
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from app.swarm.models import CompositeProduct, SwarmRun

log = logging.getLogger("x402")

_PRODUCT_FIELDS = {f.name for f in fields(CompositeProduct)}


class RedisSnapshotStore:
    """The registry snapshot in a single Redis key.

    The payload is one small JSON blob (a handful of products plus the replay
    guard), so a whole-snapshot GET/SET keeps the same semantics the file
    backend has — including the atomicity, which SET gives us for free.
    """

    def __init__(self, client: Any, key: str = "swarm:registry") -> None:
        self._client = client
        self.key = key

    def read(self) -> dict | None:
        raw = self._client.get(self.key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            log.warning("swarm registry: unreadable snapshot at %s (%s)", self.key, exc)
            return None

    def write(self, payload: dict) -> None:
        self._client.set(self.key, json.dumps(payload))

    def __str__(self) -> str:
        return f"redis:{self.key}"


class SwarmRegistry:
    def __init__(
        self,
        max_runs: int = 200,
        persist_path: str | Path | None = None,
        snapshot: RedisSnapshotStore | None = None,
    ) -> None:
        self._runs: deque[SwarmRun] = deque(maxlen=max_runs)
        self._products: dict[str, CompositeProduct] = {}
        self._sources: dict[str, dict[str, float]] = {}
        self._settled_txs: set[str] = set()  # settlement dedupe (replay guard)
        self.persist_path = Path(persist_path) if persist_path else None
        # Redis wins when present: the hosts that need it have no disk to fall
        # back to. persist_path stays live so tests can redirect file storage.
        self.snapshot = snapshot
        self._load()

    def _read_snapshot(self) -> dict | None:
        """Pull the persisted payload from whichever backend is configured."""
        if self.snapshot is not None:
            return self.snapshot.read()
        if self.persist_path is None or not self.persist_path.exists():
            return None
        try:
            return json.loads(self.persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("swarm registry: unreadable %s (%s)", self.persist_path, exc)
            return None

    def _load(self) -> None:
        data = self._read_snapshot()
        if data is None:
            return
        for raw in data.get("products", []):
            known = {k: v for k, v in raw.items() if k in _PRODUCT_FIELDS}
            try:
                product = CompositeProduct(**known)
            except TypeError as exc:
                log.warning("swarm registry: skipping product row (%s)", exc)
                continue
            self._products[product.product_id] = product
        self._settled_txs.update(
            tx for tx in data.get("settled_txs", []) if isinstance(tx, str)
        )
        if self._products:
            log.info(
                "swarm registry: restored %d listed product(s) from %s",
                len(self._products),
                self.snapshot or self.persist_path,
            )

    def save(self) -> None:
        """Persist products + settlement guard. Atomic; no-op if disabled."""
        if self.snapshot is None and self.persist_path is None:
            return
        payload = {
            "products": [asdict(p) for p in self._products.values()],
            "settled_txs": sorted(self._settled_txs),
        }
        if self.snapshot is not None:
            try:
                self.snapshot.write(payload)
            except Exception as exc:  # noqa: BLE001 — a sale must still complete
                log.error("swarm registry: persist failed to %s (%s)", self.snapshot, exc)
            return
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.persist_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
            os.replace(tmp, self.persist_path)
        except OSError as exc:
            log.warning("swarm registry: persist failed to %s (%s)", self.persist_path, exc)

    def record_settlement(self, tx: str | None) -> bool:
        """Register a settlement tx; return False if it was already recorded
        (a replay). tx=None is treated as non-idempotent and always accepted."""
        if not tx:
            return True
        if tx in self._settled_txs:
            return False
        self._settled_txs.add(tx)
        self.save()
        return True

    def add_run(self, run: SwarmRun) -> None:
        self._runs.append(run)

    def _source_entry(self, source: str) -> dict[str, float]:
        return self._sources.setdefault(
            source, {"buys": 0.0, "spend_usdc": 0.0, "revenue_usdc": 0.0}
        )

    def record_source_buy(self, source: str, spend_usdc: float) -> None:
        """Attribute an upstream purchase (cost) to a source url."""
        entry = self._source_entry(source)
        entry["buys"] += 1
        entry["spend_usdc"] = round(entry["spend_usdc"] + spend_usdc, 6)

    def record_source_revenue(self, source: str, revenue_usdc: float) -> None:
        """Attribute realized composite revenue back to a contributing source url."""
        entry = self._source_entry(source)
        entry["revenue_usdc"] = round(entry["revenue_usdc"] + revenue_usdc, 6)

    def source_scores(self) -> list[dict]:
        """Per-source profitability: revenue minus spend, best-scoring first."""
        scores = [
            {
                "source": source,
                "buys": int(entry["buys"]),
                "spend_usdc": round(entry["spend_usdc"], 6),
                "revenue_usdc": round(entry["revenue_usdc"], 6),
                "profit_score": round(entry["revenue_usdc"] - entry["spend_usdc"], 6),
            }
            for source, entry in self._sources.items()
        ]
        scores.sort(key=lambda s: s["profit_score"], reverse=True)
        return scores

    def list_product(self, product: CompositeProduct) -> None:
        self._products[product.product_id] = product
        self.save()

    def get_product(self, product_id: str) -> CompositeProduct | None:
        return self._products.get(product_id)

    def recent_runs(self, limit: int = 50) -> list[dict]:
        runs = list(self._runs)[-limit:]
        runs.reverse()
        return [r.to_dict() for r in runs]

    def products(self) -> list[dict]:
        items = sorted(
            self._products.values(), key=lambda p: p.product_id, reverse=True
        )
        return [
            {
                "product_id": p.product_id,
                "topic": p.topic,
                "cost_basis_usdc": p.cost_basis_usdc,
                "price_usdc": p.price_usdc,
                "margin_usdc": p.margin_usdc,
                "markup": p.markup,
                "network": p.network,
                "status": p.status,
                "sources": p.sources,
                "revenue_usdc": p.revenue_usdc,
            }
            for p in items
        ]


def _default_products_path() -> Path | None:
    """Resolve SWARM_PRODUCTS_FILE (default ledger/products.json, repo-relative);
    empty string disables persistence."""
    raw = os.environ.get("SWARM_PRODUCTS_FILE", "ledger/products.json")
    if not raw.strip():
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path


def _default_snapshot() -> RedisSnapshotStore | None:
    """Use Redis for the registry whenever one is configured and reachable."""
    from app import redis_client

    if redis_client.client is None:
        return None
    return RedisSnapshotStore(redis_client.client)


swarm_registry = SwarmRegistry(
    persist_path=_default_products_path(), snapshot=_default_snapshot()
)
