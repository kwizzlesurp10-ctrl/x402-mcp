"""`/swarm/revenue` must not present first-party storefront sales as swarm sales.

Issue #527: total_revenue_usdc summed the whole ledger while sold_count only
counted CompositeProduct rows, so 15 USDC sat next to "0 sold / awaiting buyers".
"""

from __future__ import annotations

import pytest

from app import ledger_io
from app.config import settings
from app.swarm import ledger_writer, sovereign
from app.swarm.models import CompositeProduct
from app.swarm.registry import swarm_registry

OPERATOR = "0x67ffc9B439aE24B0f7C7cA837C4AdfAFA06F9d38"
STRANGER = "0x7e571e959cc7c75ccdd2eac24f8775ea2eaa2f09"


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    monkeypatch.setattr(ledger_io, "LEDGER", ledger_dir)
    monkeypatch.setattr("app.ledger_store.ledger_store", None)
    return ledger_dir


@pytest.fixture
def registry():
    saved_products = dict(swarm_registry._products)
    saved_sources = dict(swarm_registry._sources)
    swarm_registry._products = {}
    swarm_registry._sources = {}
    yield swarm_registry
    swarm_registry._products = saved_products
    swarm_registry._sources = saved_sources


def _list(product_id: str, *, status: str = "listed") -> CompositeProduct:
    product = CompositeProduct(
        product_id=product_id,
        topic="t",
        cost_basis_usdc=0.03,
        price_usdc=0.09,
        markup=3.0,
        network="eip155:8453",
        sources=[],
        report="r",
        status=status,
        run_id="run-1",
    )
    swarm_registry._products[product_id] = product
    return product


def test_first_party_sales_do_not_inflate_swarm_revenue(ledger, registry, monkeypatch):
    monkeypatch.setattr(settings, "operator_wallets", OPERATOR)
    _list("composite-listed")
    ledger_writer.record_revenue(
        agent_id="mn-property-check",
        amount_usdc=15.016,
        network="eip155:8453",
        product_id="mn-property-check",
        payer=STRANGER,
    )

    rep = sovereign.build_revenue_report()

    assert rep["scope"] == "swarm_composites"
    assert rep["total_revenue_usdc"] == 0.0
    assert rep["sold_count"] == 0
    assert rep["listed_count"] == 1
    assert rep["listed_unsold_count"] == 1
    assert rep["storefront"]["revenue_usdc"] == pytest.approx(15.016)
    assert rep["storefront"]["first_party_revenue_usdc"] == pytest.approx(15.016)
    assert rep["storefront"]["swarm_revenue_usdc"] == 0.0
    assert rep["storefront"]["external_usdc"] == pytest.approx(15.016)
    assert "awaiting buyers" not in " ".join(rep["recommendations"])
    assert any("first-party SKUs" in line for line in rep["recommendations"])
    assert any("no settled sales" in line for line in rep["recommendations"])


def test_listed_composite_with_ledger_sales_counts_as_sold(ledger, registry):
    _list("pulse-listed")
    ledger_writer.record_revenue(
        agent_id="pinned-pulse-seller",
        amount_usdc=0.05,
        network="eip155:8453",
        product_id="pulse-listed",
        run_id="run-1",
        payer=STRANGER,
    )
    ledger_writer.record_revenue(
        agent_id="pinned-pulse-seller",
        amount_usdc=0.05,
        network="eip155:8453",
        product_id="pulse-listed",
        run_id="run-1",
        payer=STRANGER,
    )

    rep = sovereign.build_revenue_report()
    row = next(p for p in rep["products"] if p["product_id"] == "pulse-listed")

    assert row["status"] == "listed"
    assert row["sales_settled"] == 2
    assert row["revenue_usdc"] == pytest.approx(0.10)
    assert rep["total_revenue_usdc"] == pytest.approx(0.10)
    assert rep["sold_count"] == 1
    assert rep["listed_unsold_count"] == 0
    assert not any("no settled sales" in line for line in rep["recommendations"])
    assert not any("first-party SKUs" in line for line in rep["recommendations"])


def test_pruned_composite_with_run_id_stays_in_swarm_bucket(ledger, registry):
    """A sale whose listing was later pruned is still swarm revenue, not storefront."""
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.09,
        network="eip155:8453",
        product_id="gone-composite",
        run_id="run-old",
        payer=STRANGER,
    )

    rep = sovereign.build_revenue_report()

    assert rep["total_revenue_usdc"] == pytest.approx(0.09)
    assert rep["storefront"]["first_party_revenue_usdc"] == 0.0
    assert rep["storefront"]["swarm_revenue_usdc"] == pytest.approx(0.09)
    assert rep["sold_count"] == 0  # no current listing to mark sold


def test_operator_self_settle_is_not_folded_into_external(ledger, registry, monkeypatch):
    monkeypatch.setattr(settings, "operator_wallets", OPERATOR)
    ledger_writer.record_revenue(
        agent_id="us-rental-diligence-pack",
        amount_usdc=1.50,
        network="eip155:8453",
        product_id="us-rental-diligence-pack",
        payer=OPERATOR,
    )
    ledger_writer.record_revenue(
        agent_id="base-tx-decision",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="base-tx-decision",
        payer=STRANGER,
    )

    rep = sovereign.build_revenue_report()
    store = rep["storefront"]

    assert rep["total_revenue_usdc"] == 0.0
    assert store["revenue_usdc"] == pytest.approx(1.51)
    assert store["operator_usdc"] == pytest.approx(1.50)
    assert store["external_usdc"] == pytest.approx(0.01)
    assert store["first_party_revenue_usdc"] == pytest.approx(1.51)


def test_http_payload_keeps_the_two_books_separate(ledger, registry):
    from fastapi.testclient import TestClient

    from app.main import app

    _list("still-listed")
    ledger_writer.record_revenue(
        agent_id="mn-property-check",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="mn-property-check",
        payer=STRANGER,
    )

    body = TestClient(app).get("/swarm/revenue").json()
    assert body["total_revenue_usdc"] == 0.0
    assert body["sold_count"] == 0
    assert body["storefront"]["first_party_revenue_usdc"] == pytest.approx(0.01)
    assert body["storefront"]["revenue_usdc"] == pytest.approx(0.01)


def test_unsettled_rows_do_not_count(ledger, registry):
    _list("composite-a")
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.09,
        network="eip155:8453",
        product_id="composite-a",
        run_id="run-1",
        settled=False,
    )

    rep = sovereign.build_revenue_report()
    assert rep["total_revenue_usdc"] == 0.0
    assert rep["sold_count"] == 0
    assert rep["storefront"]["revenue_usdc"] == 0.0
