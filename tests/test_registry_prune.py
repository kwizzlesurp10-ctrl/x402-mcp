"""Pruning listings that a republish superseded.

Republishing onto a fresh id leaves the previous row behind, so a host that
used the manual /pulse/publish escape hatch a few times accumulates
near-identical listings. Pruning has to clear those without ever touching a
row that carries history.
"""

from __future__ import annotations

from app.swarm.models import CompositeProduct
from app.swarm.publisher import PULSE_TOPIC_PREFIX
from app.swarm.registry import SwarmRegistry

PINNED = "d22bbf5f3c4b4666a6f80980c7bc7c50"


def _pulse(product_id: str, block: int, **overrides) -> CompositeProduct:
    defaults = dict(
        product_id=product_id,
        topic=f"{PULSE_TOPIC_PREFIX}{block}",
        cost_basis_usdc=0.0,
        price_usdc=0.05,
        markup=0.0,
        network="eip155:8453",
        sources=["https://mainnet.base.org"],
        report="# report",
        status="listed",
        seller_agent_id="pinned-pulse-seller",
        ltv_cac_projected=0.0,
        revenue_usdc=0.0,
    )
    defaults.update(overrides)
    return CompositeProduct(**defaults)


def _registry(*products: CompositeProduct) -> SwarmRegistry:
    registry = SwarmRegistry(persist_path=None, snapshot=None)
    for product in products:
        registry.list_product(product)
    return registry


def test_prunes_superseded_duplicates() -> None:
    registry = _registry(
        _pulse(PINNED, 49424349, revenue_usdc=0.35),
        _pulse("aaa", 48957468),
        _pulse("bbb", 48957469),
    )
    removed = registry.prune_superseded(PINNED, PULSE_TOPIC_PREFIX)
    assert sorted(removed) == ["aaa", "bbb"]
    assert [p["product_id"] for p in registry.products()] == [PINNED]


def test_never_prunes_the_pinned_listing() -> None:
    """Even with no revenue, the cataloged id must survive — buyers hold its URL."""
    registry = _registry(_pulse(PINNED, 49424349))
    assert registry.prune_superseded(PINNED, PULSE_TOPIC_PREFIX) == []
    assert registry.get_product(PINNED) is not None


def test_never_prunes_a_listing_that_earned() -> None:
    registry = _registry(
        _pulse(PINNED, 49424349),
        _pulse("earner", 48957468, revenue_usdc=0.25),
    )
    assert registry.prune_superseded(PINNED, PULSE_TOPIC_PREFIX) == []
    assert registry.get_product("earner") is not None


def test_never_prunes_a_sold_listing() -> None:
    """A sold row is the record of a real sale, not clutter."""
    registry = _registry(
        _pulse(PINNED, 49424349),
        _pulse("sold", 48957468, status="sold"),
    )
    assert registry.prune_superseded(PINNED, PULSE_TOPIC_PREFIX) == []
    assert registry.get_product("sold") is not None


def test_never_prunes_a_different_product_family() -> None:
    """A composite the swarm listed is not a superseded Pulse."""
    registry = _registry(
        _pulse(PINNED, 49424349),
        _pulse("composite", 0, topic="x402 research report on agent payments"),
    )
    assert registry.prune_superseded(PINNED, PULSE_TOPIC_PREFIX) == []
    assert registry.get_product("composite") is not None


def test_prune_is_a_noop_when_nothing_is_superseded(tmp_path) -> None:
    """No rows to drop must not rewrite the snapshot."""
    path = tmp_path / "products.json"
    registry = SwarmRegistry(persist_path=path, snapshot=None)
    registry.list_product(_pulse(PINNED, 49424349))
    before = path.read_text(encoding="utf-8")
    assert registry.prune_superseded(PINNED, PULSE_TOPIC_PREFIX) == []
    assert path.read_text(encoding="utf-8") == before


def test_prune_persists(tmp_path) -> None:
    path = tmp_path / "products.json"
    registry = SwarmRegistry(persist_path=path, snapshot=None)
    registry.list_product(_pulse(PINNED, 49424349))
    registry.list_product(_pulse("aaa", 48957468))
    registry.prune_superseded(PINNED, PULSE_TOPIC_PREFIX)

    reloaded = SwarmRegistry(persist_path=path, snapshot=None)
    assert [p["product_id"] for p in reloaded.products()] == [PINNED]
