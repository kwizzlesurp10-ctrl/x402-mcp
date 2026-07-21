"""Swarm registry on Redis — listings and per-product revenue survive a restart.

The file backend is only as durable as the host's disk. On the public storefront
there isn't one: a restart on 2026-07-21 brought the registry back empty, so a
product that had genuinely sold twice reported $0.00 earned. These cover the
Redis backend that closes that gap.

Uses fakeredis; no live Redis server is required (or allowed) on this host.
"""

from __future__ import annotations

import fakeredis
import pytest

from app.swarm.models import CompositeProduct
from app.swarm.registry import RedisSnapshotStore, SwarmRegistry


@pytest.fixture
def client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


def _product(product_id: str = "p1", **over) -> CompositeProduct:
    fields = {
        "product_id": product_id,
        "topic": "Base Network Pulse @ block 1",
        "cost_basis_usdc": 0.0,
        "price_usdc": 0.25,
        "markup": 0.0,
        "network": "eip155:8453",
        "sources": ["https://mainnet.base.org"],
        "report": "report body",
        "status": "listed",
        "seller_requirements": {"pay_to": "0xabc", "payment_required_header": "hdr"},
    }
    fields.update(over)
    return CompositeProduct(**fields)


def test_a_sold_products_revenue_survives_a_restart(client) -> None:
    """The exact regression: revenue must not reset to zero on restart."""
    first = SwarmRegistry(snapshot=RedisSnapshotStore(client))
    product = _product(status="sold", revenue_usdc=0.5)
    first.list_product(product)

    second = SwarmRegistry(snapshot=RedisSnapshotStore(client))
    restored = second.get_product("p1")

    assert restored is not None
    assert restored.status == "sold"
    assert restored.revenue_usdc == 0.5
    # The challenge header is what makes the purchase URL answer 402, not 409.
    assert restored.seller_requirements["payment_required_header"] == "hdr"


def test_the_replay_guard_survives_a_restart(client) -> None:
    """Without this a restart lets an old settlement tx re-credit revenue."""
    first = SwarmRegistry(snapshot=RedisSnapshotStore(client))
    first.list_product(_product())
    assert first.record_settlement("0xtx1") is True

    second = SwarmRegistry(snapshot=RedisSnapshotStore(client))

    assert second.record_settlement("0xtx1") is False
    assert second.record_settlement("0xtx2") is True


def test_redis_wins_over_a_configured_file(client, tmp_path) -> None:
    """Hosts that need Redis have no disk to fall back to; it must take priority."""
    path = tmp_path / "products.json"
    registry = SwarmRegistry(persist_path=path, snapshot=RedisSnapshotStore(client))
    registry.list_product(_product())

    assert not path.exists()
    assert client.get("swarm:registry")


def test_an_empty_redis_yields_an_empty_registry(client) -> None:
    assert SwarmRegistry(snapshot=RedisSnapshotStore(client)).products() == []


def test_a_corrupt_snapshot_does_not_stop_startup(client) -> None:
    """Boot must survive garbage in the key — an empty catalog beats a crash."""
    client.set("swarm:registry", "{not json")

    registry = SwarmRegistry(snapshot=RedisSnapshotStore(client))

    assert registry.products() == []


def test_a_write_failure_does_not_sink_the_sale(client, monkeypatch) -> None:
    """Persistence is best-effort: the settlement already moved real money."""
    registry = SwarmRegistry(snapshot=RedisSnapshotStore(client))

    def _boom(*args, **kwargs):
        raise ConnectionError("redis went away mid-sale")

    monkeypatch.setattr(registry.snapshot, "write", _boom)

    registry.list_product(_product())  # must not raise
    assert registry.get_product("p1") is not None


def test_unknown_fields_in_a_snapshot_are_ignored(client) -> None:
    """A row written by a newer version must not break an older one."""
    import json

    client.set(
        "swarm:registry",
        json.dumps(
            {
                "products": [
                    {
                        "product_id": "p2",
                        "topic": "t",
                        "cost_basis_usdc": 0.0,
                        "price_usdc": 0.1,
                        "markup": 0.0,
                        "network": "eip155:8453",
                        "sources": [],
                        "report": "r",
                        "some_future_field": "ignored",
                    }
                ]
            }
        ),
    )

    assert SwarmRegistry(snapshot=RedisSnapshotStore(client)).get_product("p2")
