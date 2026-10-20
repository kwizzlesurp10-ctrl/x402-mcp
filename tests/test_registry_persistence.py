"""Product-registry persistence — listings survive a restart."""

from __future__ import annotations

import json

from app.swarm.models import CompositeProduct
from app.swarm.registry import SwarmRegistry


def _product(product_id: str = "p1") -> CompositeProduct:
    return CompositeProduct(
        product_id=product_id,
        topic="test topic",
        cost_basis_usdc=0.0,
        price_usdc=0.25,
        markup=0.0,
        network="eip155:8453",
        sources=["https://example.test/source"],
        report="line one\nline two",
        status="listed",
        seller_requirements={"pay_to": "0xabc", "payment_required_header": "hdr"},
    )


def test_round_trip_across_instances(tmp_path) -> None:
    path = tmp_path / "products.json"
    first = SwarmRegistry(persist_path=path)
    first.list_product(_product())
    assert first.record_settlement("0xtx1") is True

    second = SwarmRegistry(persist_path=path)
    restored = second.get_product("p1")
    assert restored is not None
    assert restored.price_usdc == 0.25
    assert restored.seller_requirements["payment_required_header"] == "hdr"
    # replay guard survives the restart too
    assert second.record_settlement("0xtx1") is False


def test_sold_state_persists(tmp_path) -> None:
    path = tmp_path / "products.json"
    first = SwarmRegistry(persist_path=path)
    product = _product()
    first.list_product(product)
    product.status = "sold"
    product.revenue_usdc = 0.25
    first.save()

    second = SwarmRegistry(persist_path=path)
    restored = second.get_product("p1")
    assert restored.status == "sold"
    assert restored.revenue_usdc == 0.25


def test_corrupt_file_yields_empty_registry(tmp_path) -> None:
    path = tmp_path / "products.json"
    path.write_text("{not json", encoding="utf-8")
    registry = SwarmRegistry(persist_path=path)
    assert registry.products() == []


def test_unknown_fields_ignored(tmp_path) -> None:
    path = tmp_path / "products.json"
    row = {
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
    path.write_text(json.dumps({"products": [row]}), encoding="utf-8")
    registry = SwarmRegistry(persist_path=path)
    assert registry.get_product("p2") is not None


def test_no_path_means_no_files(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    registry = SwarmRegistry()
    registry.list_product(_product("p3"))
    assert registry.record_settlement("0xtx2") is True
    assert list(tmp_path.iterdir()) == []
