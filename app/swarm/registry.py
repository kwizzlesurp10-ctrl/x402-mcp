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

    def add_run(self, run: SwarmRun) -> None:
        self._runs.append(run)

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
