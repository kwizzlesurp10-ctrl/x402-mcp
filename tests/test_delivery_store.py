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


def test_redis_trim_deletes_orphan_tx_keys(redis_delivery, monkeypatch) -> None:
    monkeypatch.setattr(delivery_store, "MAX_RECORDS", 3)
    client = redis_delivery._client
    for i in range(5):
        delivery_store.try_record_delivery(
            tx=f"0x{i:04d}",
            route="r",
            request_input={"n": i},
            response_body={"n": i},
        )
    assert int(client.zcard(delivery_store.INDEX_KEY)) == 3
    assert delivery_store.get_delivery("0x0000") is None
    assert delivery_store.get_delivery("0x0001") is None
    assert client.get(f"{delivery_store.RECORD_PREFIX}0x0000") is None
    assert delivery_store.get_delivery("0x0004") is not None
    listed = delivery_store.list_deliveries(limit=10)["items"]
    txs = {item["tx"] for item in listed}
    assert "0x0000" not in txs
    assert "0x0004" in txs


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


def test_should_not_capture_sse_or_non_pilot() -> None:
    from unittest.mock import MagicMock

    from starlette.responses import JSONResponse, StreamingResponse

    from app import x402_middleware_pilot

    sse_req = MagicMock()
    sse_req.url.path = "/events"
    sse = StreamingResponse(iter([]), media_type="text/event-stream", status_code=200)
    sse.headers["PAYMENT-RESPONSE"] = "ignored"
    assert x402_middleware_pilot._should_capture_delivery_body(sse_req, sse) is False

    pilot_unpaid = MagicMock()
    pilot_unpaid.url.path = "/pilot/ping"
    assert (
        x402_middleware_pilot._should_capture_delivery_body(
            pilot_unpaid, JSONResponse({"x": 1}, status_code=402)
        )
        is False
    )

    health = MagicMock()
    health.url.path = "/health"
    paid = JSONResponse({"ok": True}, status_code=200)
    paid.headers["PAYMENT-RESPONSE"] = "hdr"
    assert x402_middleware_pilot._should_capture_delivery_body(health, paid) is False


def test_should_capture_paid_pilot_success() -> None:
    from unittest.mock import MagicMock

    from starlette.responses import JSONResponse

    from app import x402_middleware_pilot

    req = MagicMock()
    req.url.path = "/pilot/ping"
    resp = JSONResponse({"ok": True}, status_code=200)
    resp.headers["PAYMENT-RESPONSE"] = "hdr"
    assert x402_middleware_pilot._should_capture_delivery_body(req, resp) is True


@pytest.mark.anyio
async def test_materialize_response_buffers_streaming_body() -> None:
    from starlette.responses import StreamingResponse

    from app import x402_middleware_pilot

    async def stream():
        yield b'{"ok":'
        yield b"true}"

    original = StreamingResponse(stream(), media_type="application/json", status_code=200)
    wrapped, body = await x402_middleware_pilot._materialize_response(original)
    assert body == b'{"ok":true}'
    assert wrapped.body == b'{"ok":true}'


@pytest.mark.anyio
async def test_middleware_delivery_records_materialized_body(monkeypatch) -> None:
    import base64
    import json
    from unittest.mock import MagicMock

    from starlette.responses import StreamingResponse

    from app import x402_middleware_pilot

    settlement = {"transaction": "0xstream", "amount": "10000", "network": "eip155:8453"}
    payment_hdr = base64.b64encode(json.dumps(settlement).encode()).decode()

    async def stream():
        yield b'{"pattern":'
        yield b'"pilot"}'

    response = StreamingResponse(stream(), status_code=200)
    response.headers["PAYMENT-RESPONSE"] = payment_hdr

    request = MagicMock()
    request.url.path = "/pilot/ping"
    request.query_params = {}

    recorded: dict[str, object] = {}

    def fake_try(**kwargs):
        recorded.update(kwargs)
        return "ledger:delivery:tx:0xstream"

    import app.delivery_store as ds

    monkeypatch.setattr(ds, "try_record_delivery", fake_try)
    monkeypatch.setattr(settings, "middleware_pilot_price", "$0.001")

    _wrapped, body = await x402_middleware_pilot._materialize_response(response)
    x402_middleware_pilot.record_middleware_delivery(request, _wrapped, body_bytes=body)
    assert recorded.get("response_body") == {"pattern": "pilot"}
    assert recorded.get("tx") == "0xstream"