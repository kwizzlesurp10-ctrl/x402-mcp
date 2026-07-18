"""Registry of swarm runs and listed composite products.

Runs and source scores mirror the app's other stores (quota_store, ops_events)
— ephemeral, capped, lost on restart. Listed products and the settlement
replay guard persist to a JSON file (`SWARM_PRODUCTS_FILE`, default
`ledger/products.json`, git-ignored) so a restart doesn't silently unlist the
catalog; set the var to an empty string to disable. Restart durability is
bounded by the host filesystem — on ephemeral hosts mount a disk or use Redis.
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from dataclasses import asdict, fields
from pathlib import Path

from app.swarm.models import CompositeProduct, SwarmRun

log = logging.getLogger("x402")

_PRODUCT_FIELDS = {f.name for f in fields(CompositeProduct)}


class SwarmRegistry:
    def __init__(
        self, max_runs: int = 200, persist_path: str | Path | None = None
    ) -> None:
        self._runs: deque[SwarmRun] = deque(maxlen=max_runs)
        self._products: dict[str, CompositeProduct] = {}
        self._sources: dict[str, dict[str, float]] = {}
        self._settled_txs: set[str] = set()  # settlement dedupe (replay guard)
        self.persist_path = Path(persist_path) if persist_path else None
        self._load()

    def _load(self) -> None:
        if self.persist_path is None or not self.persist_path.exists():
            return
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("swarm registry: unreadable %s (%s)", self.persist_path, exc)
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
                self.persist_path,
            )

    def save(self) -> None:
        """Persist products + settlement guard. Atomic write; no-op if disabled."""
        if self.persist_path is None:
            return
        payload = {
            "products": [asdict(p) for p in self._products.values()],
            "settled_txs": sorted(self._settled_txs),
        }
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


swarm_registry = SwarmRegistry(persist_path=_default_products_path())
