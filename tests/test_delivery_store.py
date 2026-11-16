"""Delivery ledger: persist input+body per settled tx, operator read API."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app import delivery_store, ledger_store, redis_client
from app.config import settings
from app.ledger_store import RedisLedgerStore
from app.main import app
from app.swarm import ledger_writer


@pytest.fixture
def redis_delivery(monkeypatch) -> RedisLedgerStore:
    store = RedisLedgerStore(fakeredis.FakeRedis(decode_responses=True))
    client = store._client
    monkeypatch.setattr(redis_client, "client", client)
    monkeypatch.setattr(ledger_store, "ledger_store", store)
    return store


def test_delivery_written_on_successful_settle(redis_delivery) -> None:
    body = {"verdict": "ok", "x" * 10: "y"}
    row = ledger_writer.record_revenue(
        agent_id="mn-property-check",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="mn-property-check",
        tx="0xabc123",
        payer="0xBuyer",
        request_input={"address": "1 Main", "city": "mn"},
        response_body=body,
    )
    assert row.get("delivery_ref") == delivery_store.delivery_ref_for_tx("0xabc123")
    rec = delivery_store.get_delivery("0xabc123")
    assert rec is not None
    assert rec["request_input"]["address"] == "1 Main"
    assert rec["response_body"]["verdict"] == "ok"
    assert rec["response_sha256"]
    assert rec["response_truncated"] is False


def test_no_delivery_without_response_body(redis_delivery) -> None:
    row = ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="p1",
        tx="0xnodata",
    )
    assert "delivery_ref" not in row
    assert delivery_store.get_delivery("0xnodata") is None


def test_truncation_flags_large_body(redis_delivery) -> None:
    huge = {"blob": "z" * (delivery_store.MAX_BODY_BYTES + 500)}
    row = ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.05,
        network="eip155:8453",
        product_id="p1",
        tx="0xlarge",
        request_input={},
        response_body=huge,
    )
    assert row.get("delivery_ref")
    rec = delivery_store.get_delivery("0xlarge")
    assert rec is not None
    assert rec["response_truncated"] is True
    assert rec["response_bytes"] == delivery_store.MAX_BODY_BYTES


def test_redis_failure_does_not_break_record_revenue(redis_delivery, monkeypatch) -> None:
    monkeypatch.setattr(delivery_store, "try_record_delivery", lambda **_k: None)
    row = ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="p1",
        tx="0xfail",
        request_input={"a": 1},
        response_body={"ok": True},
    )
    assert row["tx"] == "0xfail"
    assert "delivery_ref" not in row


def test_paid_delivery_503_does_not_write_delivery(monkeypatch) -> None:
    from app.city_compliance import paid_delivery

    spec = MagicMock()
    spec.code = "mn"

    async def verify_ok(*_a):
        return {"is_valid": True}

    async def settle_ok(*_a):
        return {"is_valid": True, "payment_settled": True, "settlement": {"transaction": "0x1"}}

    async def upstream_fail(_addr):
        raise RuntimeError("boom")

    mod = MagicMock()
    mod.check_property = upstream_fail

    recorded: list[str] = []

    def record(*_args, **_kwargs):
        recorded.append("revenue")

    monkeypatch.setattr(delivery_store, "try_record_delivery", lambda **_k: recorded.append("delivery"))

    import asyncio

    resp = asyncio.run(
        paid_delivery.deliver_paid_city_report(
            signature="sig",
            payment_required="hdr",
            mod=mod,
            spec=spec,
            address="1 Main",
            product_id="mn-property-check",
            price="$0.01",
            verify_payment=verify_ok,
            settle_payment=settle_ok,
            notify_error=lambda **_k: None,
            notify_success=lambda **_k: None,
            record_revenue=record,
            log_prefix="test",
        )
    )
    assert resp.status_code == 503
    assert recorded == []


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_admin_deliveries_rejects_without_auth(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "operator_token", "x" * 32)
    r = client.get("/admin/deliveries")
    assert r.status_code == 401


def test_admin_deliveries_list_with_auth(client, monkeypatch, redis_delivery) -> None:
    token = "operator-token-for-delivery-tests-32"
    monkeypatch.setattr(settings, "operator_token", token)
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.01,
        network="eip155:8453",
        product_id="p1",
        tx="0xlistme",
        request_input={"k": "v"},
        response_body={"r": 1},
    )
    r = client.get("/admin/deliveries", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any(item["tx"] == "0xlistme" for item in data["items"])

    one = client.get("/admin/deliveries/0xlistme", headers={"Authorization": f"Bearer {token}"})
    assert one.status_code == 200
    assert one.json()["response_body"] == {"r": 1}