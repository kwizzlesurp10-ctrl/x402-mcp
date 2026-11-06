"""MCP commerce settlement: Redis-backed idempotency (fakeredis, no live Redis)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fakeredis
import pytest

from app import mcp_server, mcp_x402_payment, x402_services
from app import mcp_settlement_store
from app.commerce import InMemoryQuotaStore


@pytest.fixture
def pay_to(monkeypatch: pytest.MonkeyPatch) -> str:
    addr = "0xTestPayTo00000000000000000000000001"
    monkeypatch.setattr(mcp_x402_payment.settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(mcp_x402_payment.settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(mcp_x402_payment.settings, "x402_default_network", "eip155:84532")
    monkeypatch.setattr(x402_services.settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(x402_services.settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(x402_services.settings, "x402_default_network", "eip155:84532")
    return addr


def _fake_ctx(payment: dict | None) -> SimpleNamespace:
    from x402.mcp.constants import MCP_PAYMENT_META_KEY

    extra = {MCP_PAYMENT_META_KEY: payment} if payment is not None else {}
    meta = SimpleNamespace(model_extra=extra)
    request_context = SimpleNamespace(meta=meta)
    return SimpleNamespace(request_context=request_context)


def _valid_payload_dict(built: dict) -> dict:
    from x402.http import decode_payment_required_header

    pr = decode_payment_required_header(built["payment_required_header"])
    accept = pr.accepts[0]
    return {
        "x402Version": 2,
        "payload": {"signature": "0xsig", "authorization": {}},
        "accepted": accept.model_dump(by_alias=True, exclude_none=True),
    }


@pytest.fixture(autouse=True)
def _redis_settlement(monkeypatch: pytest.MonkeyPatch) -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(mcp_settlement_store, "_CLIENT", client)


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.commerce_payment import clear_commerce_challenges

    clear_commerce_challenges()
    mcp_x402_payment.clear_mcp_settlement_cache()
    if mcp_settlement_store._CLIENT:  # noqa: SLF001
        mcp_settlement_store.clear_mcp_settlement_redis_test()
    yield
    clear_commerce_challenges()
    mcp_x402_payment.clear_mcp_settlement_cache()


@pytest.mark.asyncio
async def test_two_workers_single_settle_via_redis_cache(
    pay_to: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = InMemoryQuotaStore()
    monkeypatch.setattr(mcp_server, "quota_store", store)
    monkeypatch.setattr(x402_services, "quota_store", store)

    built = x402_services.build_pro_upgrade_requirements("mcp-redis-dup")
    payment = _valid_payload_dict(built)

    mock_server = MagicMock()
    mock_server.find_matching_requirements = MagicMock(return_value=built["requirements"][0])
    mock_verify = MagicMock()
    mock_verify.is_valid = True
    mock_server.verify_payment = AsyncMock(return_value=mock_verify)
    mock_settle = MagicMock()
    mock_settle.success = True
    mock_settle.model_dump.return_value = {
        "success": True,
        "transaction": "0xredis_once",
        "network": "eip155:84532",
    }
    mock_server.settle_payment = AsyncMock(return_value=mock_settle)
    monkeypatch.setattr(x402_services, "_resource_server", lambda _net=None: mock_server)

    ctx = _fake_ctx(payment)
    first = await mcp_server.activate_pro_tier(agent_id="mcp-redis-dup", ctx=ctx)
    second = await mcp_server.activate_pro_tier(agent_id="mcp-redis-dup", ctx=ctx)

    assert first.isError is False
    assert second.isError is False
    assert mock_server.settle_payment.await_count == 1

    client = mcp_settlement_store._CLIENT  # noqa: SLF001
    assert client is not None
    keys = list(client.scan_iter(match="mcp_settle:*", count=64))
    assert keys, "expected a redis cache key for successful settlement"
    raw = client.get(keys[0])
    assert raw
    body = json.loads(raw)
    assert body["payment_settled"] is True


@pytest.mark.asyncio
async def test_contention_wait_returns_peer_result(monkeypatch: pytest.MonkeyPatch) -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(mcp_settlement_store, "_CLIENT", client)

    key = "abc" * 10
    peer_result = {"payment_settled": True, "settlement": {"success": True, "transaction": "0xpeer"}}
    assert mcp_settlement_store.try_cache_settlement(key, peer_result)

    monkeypatch.setattr(mcp_settlement_store, "acquire_settlement_lock", lambda _k, ttl_seconds=90: False)
    monkeypatch.setattr(mcp_settlement_store, "wait_for_cached_settlement", lambda _k, **kw: peer_result)

    from app.commerce_payment import clear_commerce_challenges

    clear_commerce_challenges()
    mcp_x402_payment.clear_mcp_settlement_cache()

    pay_to = "0x" + "ab" * 20
    monkeypatch.setattr(mcp_x402_payment.settings, "x402_pay_to_address", pay_to)
    monkeypatch.setattr(x402_services.settings, "x402_pay_to_address", pay_to)
    monkeypatch.setattr(mcp_x402_payment.settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(x402_services.settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(mcp_x402_payment.settings, "x402_default_network", "eip155:84532")
    monkeypatch.setattr(x402_services.settings, "x402_default_network", "eip155:84532")

    built = x402_services.build_pro_upgrade_requirements("contention-wait")
    payment = _valid_payload_dict(built)
    mock_server = MagicMock()
    mock_server.find_matching_requirements = MagicMock(return_value=built["requirements"][0])
    mock_server.verify_payment = AsyncMock()
    mock_server.settle_payment = AsyncMock()
    monkeypatch.setattr(x402_services, "_resource_server", lambda _net=None: mock_server)

    out = await mcp_x402_payment.verify_and_settle_mcp_payload(
        payment,
        x402_services.resolve_pro_authoritative_header(
            "contention-wait",
            rebuild=lambda: x402_services.build_pro_upgrade_requirements("contention-wait"),
        ),
    )
    assert out["payment_settled"] is True
    assert out["settlement"]["transaction"] == "0xpeer"
    mock_server.settle_payment.assert_not_awaited()
