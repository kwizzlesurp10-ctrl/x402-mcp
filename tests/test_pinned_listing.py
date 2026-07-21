"""Pinned listing — the cataloged purchase URL survives an ephemeral-host restart.

The Bazaar catalog indexes the purchase URL, which embeds the product_id. On a
host with no persistent disk (Render free), a restart wipes products.json, so a
fresh uuid per boot would strand every buyer who found us through discovery on a
404. Republishing onto the pinned id keeps that URL answering 402.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.swarm import publisher
from app.swarm.models import CompositeProduct
from app.swarm.registry import SwarmRegistry

PINNED = "d22bbf5f3c4b4666a6f80980c7bc7c50"


@pytest.fixture
def registry(tmp_path, monkeypatch) -> SwarmRegistry:
    """An empty registry standing in for the one a cold start comes back with."""
    reg = SwarmRegistry(persist_path=tmp_path / "products.json")
    monkeypatch.setattr(publisher, "swarm_registry", reg)
    return reg


@pytest.fixture
def stub_publish(monkeypatch) -> list[str | None]:
    """Record the product_id publish_pulse_product is called with; skip real I/O."""
    calls: list[str | None] = []

    async def _fake(agent_id, price_usdc=None, product_id=None):
        calls.append(product_id)
        return CompositeProduct(
            product_id=product_id or "generated",
            topic="Base Network Pulse @ block 1",
            cost_basis_usdc=0.0,
            price_usdc=0.25,
            markup=0.0,
            network="eip155:8453",
            sources=[],
            report="report",
            status="listed",
            seller_agent_id=agent_id,
            seller_requirements={"payment_required_header": "hdr"},
        )

    monkeypatch.setattr(publisher, "publish_pulse_product", _fake)
    return calls


@pytest.mark.asyncio
async def test_republishes_onto_the_pinned_id_when_the_registry_is_empty(
    registry, stub_publish, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "pinned_pulse_product_id", PINNED)

    product = await publisher.restore_pinned_listing()

    assert stub_publish == [PINNED]
    assert product is not None
    # Same id => same purchase URL => the catalog entry still resolves.
    assert product.product_id == PINNED


@pytest.mark.asyncio
async def test_keeps_the_surviving_listing_instead_of_republishing(
    registry, stub_publish, monkeypatch
) -> None:
    """A host that did keep its disk must not lose the sale history to a rebuild."""
    monkeypatch.setattr(settings, "pinned_pulse_product_id", PINNED)
    survivor = CompositeProduct(
        product_id=PINNED,
        topic="Base Network Pulse @ block 48915100",
        cost_basis_usdc=0.0,
        price_usdc=0.25,
        markup=0.0,
        network="eip155:8453",
        sources=[],
        report="report",
        status="sold",
        revenue_usdc=0.5,
        seller_requirements={"payment_required_header": "hdr"},
    )
    registry.list_product(survivor)

    product = await publisher.restore_pinned_listing()

    assert stub_publish == []
    assert product is survivor
    assert product.revenue_usdc == 0.5


@pytest.mark.asyncio
async def test_republishes_when_the_restored_row_cannot_be_sold(
    registry, stub_publish, monkeypatch
) -> None:
    """A row without a challenge header serves 409, not 402 — rebuild it."""
    monkeypatch.setattr(settings, "pinned_pulse_product_id", PINNED)
    registry.list_product(
        CompositeProduct(
            product_id=PINNED,
            topic="stale",
            cost_basis_usdc=0.0,
            price_usdc=0.25,
            markup=0.0,
            network="eip155:8453",
            sources=[],
            report="report",
            status="draft",
            seller_requirements=None,
        )
    )

    await publisher.restore_pinned_listing()

    assert stub_publish == [PINNED]


@pytest.mark.asyncio
async def test_disabled_by_default(registry, stub_publish, monkeypatch) -> None:
    monkeypatch.setattr(settings, "pinned_pulse_product_id", "")

    assert await publisher.restore_pinned_listing() is None
    assert stub_publish == []


@pytest.mark.asyncio
async def test_a_failed_republish_never_breaks_the_boot(
    registry, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "pinned_pulse_product_id", PINNED)

    async def _boom(*args, **kwargs):
        raise RuntimeError("base rpc unreachable")

    monkeypatch.setattr(publisher, "publish_pulse_product", _boom)

    assert await publisher.restore_pinned_listing() is None
