"""Demand instrumentation: count the 402s, not just the sales.

Without this, "nobody has ever seen this listing" and "forty agents priced it
and walked away" are indistinguishable — and they imply opposite next moves.
"""

from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app import demand, ledger_io, redis_client
from app.config import settings
from app.main import app
from app.swarm import ledger_writer

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_memory(monkeypatch):
    """Isolate the in-memory fallback between tests."""
    monkeypatch.setattr(demand, "_memory", demand.Counter())
    monkeypatch.setattr(demand, "_memory_last", {})
    monkeypatch.setattr(redis_client, "client", None)


@pytest.fixture
def redis_backed(monkeypatch):
    monkeypatch.setattr(
        redis_client, "client", fakeredis.FakeRedis(decode_responses=True)
    )


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    d = tmp_path / "ledger"
    d.mkdir()
    monkeypatch.setattr(ledger_io, "LEDGER", d)
    return d


def test_counts_accumulate_per_resource() -> None:
    demand.record_challenge("pulse-1")
    demand.record_challenge("pulse-1")
    demand.record_challenge("mn-property-check")

    assert demand.challenges() == {"pulse-1": 2, "mn-property-check": 1}


def test_counts_survive_a_restart_when_redis_backed(redis_backed, monkeypatch) -> None:
    """The whole point of putting this in Redis rather than memory."""
    demand.record_challenge("pulse-1")
    demand.record_challenge("pulse-1")
    # A restart clears process memory but not Redis.
    monkeypatch.setattr(demand, "_memory", demand.Counter())

    assert demand.challenges()["pulse-1"] == 2


def test_recording_never_raises(monkeypatch) -> None:
    """A counter must never be able to fail a sale."""

    class Broken:
        def pipeline(self):
            raise ConnectionError("redis gone")

    monkeypatch.setattr(redis_client, "client", Broken())

    demand.record_challenge("pulse-1")  # must not raise


def test_an_empty_key_is_ignored() -> None:
    demand.record_challenge("")

    assert demand.challenges() == {}


def test_report_joins_challenges_to_settled_sales(ledger) -> None:
    for _ in range(10):
        demand.record_challenge("pulse-1")
    demand.record_challenge("ignored-by-everyone")
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.05,
        network="eip155:8453",
        product_id="pulse-1",
        tx="0xabc",
    )

    report = demand.build_report()
    rows = {r["resource"]: r for r in report["resources"]}

    assert rows["pulse-1"]["challenges_served"] == 10
    assert rows["pulse-1"]["sales_settled"] == 1
    assert rows["pulse-1"]["conversion"] == 0.1
    assert rows["pulse-1"]["revenue_usdc"] == 0.05
    # A resource nobody bought is still reported — that is the useful signal.
    assert rows["ignored-by-everyone"]["sales_settled"] == 0
    assert rows["ignored-by-everyone"]["conversion"] == 0.0
    assert report["overall_conversion"] == round(1 / 11, 4)


def test_sales_predating_the_counter_do_not_inflate_conversion(ledger) -> None:
    """The live bug: counting started tonight, the ledger held older sales, and
    dividing one by the other reported a 200% conversion rate."""
    ledger_writer.record_revenue(  # settled long before counting began
        agent_id="seller",
        amount_usdc=0.25,
        network="eip155:8453",
        product_id="pulse-1",
        tx="0xold",
    )
    import json

    path = ledger.joinpath("revenue.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["ts"] = "2020-01-01T00:00:00+00:00"
    path.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")

    demand.record_challenge("pulse-1")  # counting starts now

    row = next(r for r in demand.build_report()["resources"] if r["resource"] == "pulse-1")

    assert row["sales_settled"] == 1  # history is still reported...
    assert row["sales_in_window"] == 0  # ...but not counted against new views
    assert row["conversion"] == 0.0
    assert row["conversion"] <= 1.0


def test_conversion_can_exceed_one_when_a_challenge_is_reused(ledger) -> None:
    """Not a bug, and worth pinning so nobody "fixes" it by clamping.

    A buyer may cache a PAYMENT-REQUIRED header and settle against it more than
    once without re-fetching the 402, so sales legitimately can outnumber
    challenges. The number to distrust is one built from sales that predate
    counting — that is what the window guards, not this.
    """
    demand.record_challenge("pulse-1")
    for i in range(5):
        ledger_writer.record_revenue(
            agent_id="seller",
            amount_usdc=0.05,
            network="eip155:8453",
            product_id="pulse-1",
            tx=f"0x{i}",
        )

    row = next(
        r for r in demand.build_report()["resources"] if r["resource"] == "pulse-1"
    )

    assert row["conversion"] == 5.0  # reported honestly, not clamped
    assert row["sales_in_window"] == 5


def test_conversion_is_none_with_no_views(ledger) -> None:
    """A ratio over zero views says nothing; do not report 0% as a finding."""
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.05,
        network="eip155:8453",
        product_id="never-challenged",
        tx="0xabc",
    )

    rows = {r["resource"]: r for r in demand.build_report()["resources"]}

    assert rows["never-challenged"]["challenges_served"] == 0
    assert rows["never-challenged"]["conversion"] is None


def test_unsettled_revenue_rows_are_not_counted_as_sales(ledger) -> None:
    demand.record_challenge("pulse-1")
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.05,
        network="eip155:8453",
        product_id="pulse-1",
        tx=None,
        settled=False,
    )

    rows = {r["resource"]: r for r in demand.build_report()["resources"]}

    assert rows["pulse-1"]["sales_settled"] == 0


# --- the live 402 paths must actually record -----------------------------------


def test_the_composite_402_records_a_challenge(monkeypatch) -> None:
    from app.swarm.models import CompositeProduct
    from app.swarm.registry import swarm_registry

    swarm_registry.list_product(
        CompositeProduct(
            product_id="counted-1",
            topic="t",
            cost_basis_usdc=0.0,
            price_usdc=0.05,
            markup=0.0,
            network="eip155:8453",
            sources=[],
            report="r",
            status="listed",
            seller_requirements={"payment_required_header": "hdr", "pay_to": "0xa"},
        )
    )

    response = client.get("/swarm/products/counted-1/purchase")

    assert response.status_code == 402
    assert demand.challenges().get("counted-1") == 1


def test_the_mn_402_records_a_challenge(monkeypatch) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", "0xabc")

    response = client.get("/mn/property-check?address=1700 Penn Ave N")

    if response.status_code == 402:  # needs a buildable challenge
        assert demand.challenges().get("mn-property-check") == 1


def test_the_endpoint_serves_the_report() -> None:
    demand.record_challenge("pulse-1")

    body = client.get("/demand").json()

    assert body["total_challenges_served"] >= 1
    assert any(r["resource"] == "pulse-1" for r in body["resources"])


# --- our own traffic must not read as demand ----------------------------------


def test_self_traffic_is_not_counted() -> None:
    """The uptime monitor hits the listing every 15 minutes. That is not a buyer."""
    assert demand.is_self_traffic({"x-demand-ignore": "storefront-monitor"}) is True
    assert demand.is_self_traffic({}) is False


def test_a_marked_request_does_not_increment(monkeypatch) -> None:
    from app.swarm.models import CompositeProduct
    from app.swarm.registry import swarm_registry

    swarm_registry.list_product(
        CompositeProduct(
            product_id="ignored-1",
            topic="t",
            cost_basis_usdc=0.0,
            price_usdc=0.05,
            markup=0.0,
            network="eip155:8453",
            sources=[],
            report="r",
            status="listed",
            seller_requirements={"payment_required_header": "hdr", "pay_to": "0xa"},
        )
    )

    response = client.get(
        "/swarm/products/ignored-1/purchase",
        headers={"X-Demand-Ignore": "storefront-monitor"},
    )

    assert response.status_code == 402  # still serves normally
    assert demand.challenges().get("ignored-1") is None  # just not counted
