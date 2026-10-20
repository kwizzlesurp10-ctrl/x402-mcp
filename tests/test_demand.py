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


OPERATOR = "0x67ffc9b4390000000000000000000000000000ab"
EXTERNAL = "0x7e81988b710000000000000000000000000000cd"


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    d = tmp_path / "ledger"
    d.mkdir()
    monkeypatch.setattr(ledger_io, "LEDGER", d)
    monkeypatch.setattr("app.ledger_store.ledger_store", None)
    return d


@pytest.fixture
def operator_configured(monkeypatch):
    """Production has OPERATOR_WALLETS set (render.yaml:60-61).

    Without it every row classifies as unknown, and conversion — which counts
    external payers only — reads 0.0. Tests that assert a non-zero conversion
    must therefore both configure this and name a payer.
    """
    monkeypatch.setattr(settings, "operator_wallets", OPERATOR)


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


def test_report_joins_challenges_to_settled_sales(ledger, operator_configured) -> None:
    for _ in range(10):
        demand.record_challenge("pulse-1")
    demand.record_challenge("ignored-by-everyone")
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.05,
        network="eip155:8453",
        product_id="pulse-1",
        tx="0xabc",
        payer=EXTERNAL,
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


def test_conversion_can_exceed_one_when_a_challenge_is_reused(
    ledger, operator_configured
) -> None:
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
            payer=EXTERNAL,
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


# --- an operator self-settle is not a sale --------------------------------------


def test_operator_settles_do_not_count_as_conversion(ledger, operator_configured) -> None:
    """The live bug this split was written for.

    mn-property-check reported 4% conversion on the strength of three settles
    the operator ran to get the resource catalogued. The CDP Bazaar's own
    quality block disagreed the whole time (l30DaysUniquePayers: 1).
    """
    for _ in range(100):
        demand.record_challenge("mn-property-check")
    for i in range(3):
        ledger_writer.record_revenue(
            agent_id="seller",
            amount_usdc=0.01,
            network="eip155:8453",
            product_id="mn-property-check",
            tx=f"0xcatalog{i}",
            payer=OPERATOR,
        )

    row = next(
        r
        for r in demand.build_report()["resources"]
        if r["resource"] == "mn-property-check"
    )

    assert row["sales_operator"] == 3
    assert row["sales_external"] == 0
    assert row["conversion"] == 0.0
    # The old number is retained so the correction is auditable.
    assert row["conversion_including_operator"] == 0.03


def test_an_external_sale_still_converts(ledger, operator_configured) -> None:
    for _ in range(10):
        demand.record_challenge("base-tx-decision")
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="base-tx-decision",
        tx="0xreal",
        payer=EXTERNAL,
    )

    row = next(
        r
        for r in demand.build_report()["resources"]
        if r["resource"] == "base-tx-decision"
    )

    assert row["sales_external"] == 1
    assert row["sales_operator"] == 0
    assert row["conversion"] == 0.1


def test_a_payerless_row_is_unknown_never_external(ledger, operator_configured) -> None:
    """Most of this project's revenue history predates payer threading."""
    for _ in range(10):
        demand.record_challenge("pulse-1")
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.05,
        network="eip155:8453",
        product_id="pulse-1",
        tx="0xold",
    )

    row = next(
        r for r in demand.build_report()["resources"] if r["resource"] == "pulse-1"
    )

    assert row["sales_unknown"] == 1
    assert row["sales_external"] == 0
    assert row["conversion"] == 0.0  # not None, and not 0.1


def test_without_operator_wallets_every_row_is_unknown(ledger, monkeypatch) -> None:
    """Fail closed: an unconfigured box must not report self-settles as sales."""
    monkeypatch.setattr(settings, "operator_wallets", "")
    for _ in range(10):
        demand.record_challenge("pulse-1")
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.05,
        network="eip155:8453",
        product_id="pulse-1",
        tx="0xabc",
        payer=EXTERNAL,
    )

    row = next(
        r for r in demand.build_report()["resources"] if r["resource"] == "pulse-1"
    )

    assert row["sales_unknown"] == 1
    assert row["sales_external"] == 0
    assert row["conversion"] == 0.0


def test_the_three_splits_always_sum_to_sales_in_window(
    ledger, operator_configured
) -> None:
    demand.record_challenge("pulse-1")
    for payer in (OPERATOR, EXTERNAL, None):
        ledger_writer.record_revenue(
            agent_id="seller",
            amount_usdc=0.05,
            network="eip155:8453",
            product_id="pulse-1",
            tx=f"0x{payer}",
            payer=payer,
        )

    row = next(
        r for r in demand.build_report()["resources"] if r["resource"] == "pulse-1"
    )

    assert (
        row["sales_external"] + row["sales_operator"] + row["sales_unknown"]
        == row["sales_in_window"]
    )


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


# --- client classification: is a view a buyer or a bot? -----------------------


def test_classify_client_buckets() -> None:
    assert demand.classify_client("x402-fetch/1.0") == "x402-client"
    assert demand.classify_client("python-httpx/0.27") == "python-http"
    assert demand.classify_client("node-fetch/3.0") == "node-http"
    assert demand.classify_client("Mozilla/5.0 (Windows) Chrome/120") == "browser"
    assert demand.classify_client("curl/8.4.0") == "crawler-bot"
    assert demand.classify_client("SomeBot/1.0 crawler") == "crawler-bot"
    assert demand.classify_client("") == "unknown"
    assert demand.classify_client(None) == "unknown"
    assert demand.classify_client("HAL9000/2001") == "other"


def test_qualified_views_exclude_bots_and_browsers(ledger, monkeypatch) -> None:
    """The whole point: separate prospective buyers from crawler noise."""
    monkeypatch.setattr(demand, "_memory_clients", {})
    demand.record_challenge("p", "x402-fetch/1.0")       # a real client
    demand.record_challenge("p", "python-httpx/0.27")    # a real client
    demand.record_challenge("p", "curl/8.4.0")           # bot
    demand.record_challenge("p", "Mozilla/5.0 Chrome")   # browser, not a payer
    demand.record_challenge("p", None)                    # unidentified

    row = next(r for r in demand.build_report()["resources"] if r["resource"] == "p")

    assert row["challenges_served"] == 5
    assert row["qualified_views"] == 2  # only the two real clients
    assert row["clients"]["x402-client"] == 1
    assert row["clients"]["crawler-bot"] == 1


def test_qualified_views_survive_redis(redis_backed, monkeypatch) -> None:
    demand.record_challenge("p", "x402-fetch/1.0")
    demand.record_challenge("p", "curl/8")
    monkeypatch.setattr(demand, "_memory_clients", {})  # simulate restart

    row = next(r for r in demand.build_report()["resources"] if r["resource"] == "p")
    assert row["qualified_views"] == 1
    assert row["clients"] == {"x402-client": 1, "crawler-bot": 1}


def test_distinct_user_agents_are_sampled_and_capped(monkeypatch) -> None:
    """Naming the actual clients is what separates an indexer from a shopper."""
    monkeypatch.setattr(demand, "_memory_ua", {})
    monkeypatch.setattr(demand, "_UA_SAMPLE_CAP", 3)
    for ua in ["x402-fetch/1", "x402-fetch/1", "httpx/0.27", "curl/8", "node-fetch/3"]:
        demand.record_challenge("p", ua)

    samples = demand.ua_samples()["p"]
    assert "x402-fetch/1" in samples and len(set(samples)) == len(samples)  # deduped
    assert len(samples) <= 3  # capped

    row = next(r for r in demand.build_report()["resources"] if r["resource"] == "p")
    assert set(row["user_agents"]) == set(samples)
