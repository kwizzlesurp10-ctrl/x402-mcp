"""MCP native x402 payment transport for commerce tools."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import mcp_server, mcp_x402_payment, x402_services
from app.commerce import InMemoryQuotaStore
from app.commerce_payment import clear_commerce_challenges
from app.config import settings
from app.mcp_x402_payment import MCP_PAYMENT_META_KEY
from x402.mcp.constants import MCP_PAYMENT_RESPONSE_META_KEY


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    clear_commerce_challenges()
    mcp_x402_payment.clear_mcp_settlement_cache()
    yield
    clear_commerce_challenges()
    mcp_x402_payment.clear_mcp_settlement_cache()


@pytest.fixture
def pay_to(monkeypatch: pytest.MonkeyPatch) -> str:
    addr = "0xTestPayTo00000000000000000000000001"
    monkeypatch.setattr(settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(settings, "x402_default_network", "eip155:84532")
    return addr


def _fake_ctx(payment: dict | None) -> SimpleNamespace:
    extra = {MCP_PAYMENT_META_KEY: payment} if payment is not None else {}
    meta = SimpleNamespace(model_extra=extra)
    request_context = SimpleNamespace(meta=meta)
    return SimpleNamespace(request_context=request_context)


def _valid_payload_dict(built: dict) -> dict:
    """Minimal PaymentPayload-shaped dict matching server accepts (for matching tests)."""
    from x402.http import decode_payment_required_header

    pr = decode_payment_required_header(built["payment_required_header"])
    accept = pr.accepts[0]
    return {
        "x402Version": 2,
        "payload": {"signature": "0xsig", "authorization": {}},
        "accepted": accept.model_dump(by_alias=True, exclude_none=True),
    }


@pytest.mark.asyncio
async def test_unpaid_activate_pro_returns_payment_required(pay_to: str) -> None:
    result = await mcp_server.activate_pro_tier(agent_id="mcp-buyer-1", ctx=None)

    assert hasattr(result, "isError")
    assert result.isError is True
    assert result.structuredContent is not None
    assert "accepts" in result.structuredContent
    assert result.structuredContent["accepts"][0]["payTo"] == pay_to


@pytest.mark.asyncio
async def test_valid_mcp_payment_executes_and_returns_receipt(
    pay_to: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = InMemoryQuotaStore()
    monkeypatch.setattr(mcp_server, "quota_store", store)
    monkeypatch.setattr(x402_services, "quota_store", store)

    built = x402_services.build_pro_upgrade_requirements("mcp-buyer-2")
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
        "transaction": "0xmcppro",
        "network": "eip155:84532",
    }
    mock_server.settle_payment = AsyncMock(return_value=mock_settle)
    monkeypatch.setattr(x402_services, "_resource_server", lambda _net=None: mock_server)

    result = await mcp_server.activate_pro_tier(
        agent_id="mcp-buyer-2",
        ctx=_fake_ctx(payment),
    )

    assert hasattr(result, "isError")
    assert result.isError is False
    assert result.meta is not None
    assert MCP_PAYMENT_RESPONSE_META_KEY in result.meta
    assert result.meta[MCP_PAYMENT_RESPONSE_META_KEY]["transaction"] == "0xmcppro"
    payload = json.loads(result.content[0].text)
    assert payload["data"]["tier"] == "pro"
    assert store.get_tier("mcp-buyer-2") == "pro"
    mock_server.settle_payment.assert_awaited_once()


@pytest.mark.asyncio
async def test_tampered_payto_rejected(pay_to: str, monkeypatch: pytest.MonkeyPatch) -> None:
    built = x402_services.build_pro_upgrade_requirements("mcp-tamper")
    payment = _valid_payload_dict(built)
    payment["accepted"]["payTo"] = "0x" + "ab" * 20

    mock_server = MagicMock()
    mock_server.find_matching_requirements = MagicMock(return_value=None)
    monkeypatch.setattr(x402_services, "_resource_server", lambda _net=None: mock_server)

    result = await mcp_server.activate_pro_tier(
        agent_id="mcp-tamper",
        ctx=_fake_ctx(payment),
    )

    assert result.isError is True
    assert "does not match" in result.structuredContent["error"]


@pytest.mark.asyncio
async def test_replay_does_not_double_settle(pay_to: str, monkeypatch: pytest.MonkeyPatch) -> None:
    store = InMemoryQuotaStore()
    monkeypatch.setattr(mcp_server, "quota_store", store)
    monkeypatch.setattr(x402_services, "quota_store", store)

    built = x402_services.build_pro_upgrade_requirements("mcp-replay")
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
        "transaction": "0xreplay",
        "network": "eip155:84532",
    }
    mock_server.settle_payment = AsyncMock(return_value=mock_settle)
    monkeypatch.setattr(x402_services, "_resource_server", lambda _net=None: mock_server)

    ctx = _fake_ctx(payment)
    first = await mcp_server.activate_pro_tier(agent_id="mcp-replay", ctx=ctx)
    second = await mcp_server.activate_pro_tier(agent_id="mcp-replay", ctx=ctx)

    assert first.isError is False
    assert second.isError is False
    assert mock_server.settle_payment.await_count == 1
