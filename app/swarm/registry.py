"""In-memory registry of swarm runs and listed composite products.

Mirrors the app's other stores (quota_store, ops_events) — ephemeral, capped,
lost on restart. Swap for Redis alongside the commerce store when persisting.
"""

from __future__ import annotations

from collections import deque

from app.swarm.models import CompositeProduct, SwarmRun


class SwarmRegistry:
    def __init__(self, max_runs: int = 200) -> None:
        self._runs: deque[SwarmRun] = deque(maxlen=max_runs)
        self._products: dict[str, CompositeProduct] = {}
        self._sources: dict[str, dict[str, float]] = {}

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


swarm_registry = SwarmRegistry()
