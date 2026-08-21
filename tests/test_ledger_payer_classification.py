"""/ledger/revenue tells a real external sale apart from an operator self-settle.

`agent_id` is a seller/product label, not a buyer identity, so it can't do this
(see the swarm's own 2026-07-25 buyer-signal audit). The facilitator's settle
response carries the actual payer address; this pins that it reaches the
ledger row and that the endpoint classifies it against OPERATOR_WALLETS.
"""

from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app import ledger_store
from app.config import settings
from app.ledger_store import RedisLedgerStore
from app.main import app
from app.swarm import ledger_writer

client = TestClient(app)

OPERATOR = "0x67ffc9B439aE24B0f7C7cA837C4AdfAFA06F9d38"
HOT_BUYER = "0x9138fEA6e13a701694D4d598000Fc3c1dE3d594C"
STRANGER = "0x7e571e959cc7c75ccdd2eac24f8775ea2eaa2f09"


@pytest.fixture
def redis_ledger(monkeypatch):
    store = RedisLedgerStore(fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(ledger_store, "ledger_store", store)
    # Drop any prior 10s /ledger response cache so each test sees this store.
    from app.main import invalidate_ledger_cache

    invalidate_ledger_cache()
    return store


@pytest.fixture
def configured_operator_wallets(monkeypatch):
    monkeypatch.setattr(settings, "operator_wallets", OPERATOR)


def test_record_revenue_lowercases_and_stores_payer(redis_ledger) -> None:
    ledger_writer.record_revenue(
        agent_id="base-tx-decision",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="base-tx-decision",
        tx="0xabc",
        payer=STRANGER.upper(),
    )
    rows = redis_ledger.read("revenue", None)
    assert rows[0]["payer"] == STRANGER.lower()


def test_record_revenue_payer_defaults_to_none(redis_ledger) -> None:
    ledger_writer.record_revenue(
        agent_id="base-tx-decision",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="base-tx-decision",
        tx="0xabc",
    )
    rows = redis_ledger.read("revenue", None)
    assert rows[0]["payer"] is None


def test_operator_payer_is_flagged_not_external(
    redis_ledger, configured_operator_wallets
) -> None:
    ledger_writer.record_revenue(
        agent_id="pinned-pulse-seller",
        amount_usdc=0.25,
        network="eip155:8453",
        product_id="pulse",
        tx="0x1",
        payer=OPERATOR,
    )
    rows = client.get("/ledger/revenue").json()
    assert rows[0]["is_operator_settle"] is True


def test_comma_separated_operator_wallets_flag_each_payer(
    redis_ledger, monkeypatch
) -> None:
    """render.yaml lists every operator spend address, comma-separated.

    The 2026-08-20 MN pay_and_fetch used buyer-hot 0x9138… which was missing
    from OPERATOR_WALLETS, so a seed settle counted as external demand.
    Classification is at read time — adding the address reclassifies old rows.
    """
    monkeypatch.setattr(
        settings, "operator_wallets", f"{OPERATOR},{HOT_BUYER}"
    )
    ledger_writer.record_revenue(
        agent_id="mn-property-check",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="mn-property-check",
        tx="0x60f1",
        payer=HOT_BUYER,
    )
    rows = client.get("/ledger/revenue").json()
    assert rows[0]["is_operator_settle"] is True
    assert rows[0]["payer"] == HOT_BUYER.lower()


def test_stranger_payer_is_flagged_external(
    redis_ledger, configured_operator_wallets
) -> None:
    ledger_writer.record_revenue(
        agent_id="base-tx-decision",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="base-tx-decision",
        tx="0x2",
        payer=STRANGER,
    )
    rows = client.get("/ledger/revenue").json()
    assert rows[0]["is_operator_settle"] is False


def test_missing_payer_is_unknown_not_external(
    redis_ledger, configured_operator_wallets
) -> None:
    """A row with no payer (old data, or a facilitator that didn't report one)
    must read as unknown, never get counted as a real sale by default."""
    ledger_writer.record_revenue(
        agent_id="mn-property-check",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="mn-property-check",
        tx="0x3",
    )
    rows = client.get("/ledger/revenue").json()
    assert rows[0]["is_operator_settle"] is None


def test_no_operator_wallets_configured_means_unknown(redis_ledger, monkeypatch) -> None:
    monkeypatch.setattr(settings, "operator_wallets", "")
    ledger_writer.record_revenue(
        agent_id="base-tx-decision",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="base-tx-decision",
        tx="0x4",
        payer=STRANGER,
    )
    rows = client.get("/ledger/revenue").json()
    assert rows[0]["is_operator_settle"] is None


def test_spend_ledger_is_not_annotated(redis_ledger, configured_operator_wallets) -> None:
    ledger_writer.record_spend(
        agent_id="a1",
        amount_usdc=0.01,
        network="eip155:8453",
        url="https://upstream.test/search",
        run_id="run-1",
    )
    rows = client.get("/ledger/spend").json()
    assert "is_operator_settle" not in rows[0]
