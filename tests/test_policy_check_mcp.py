"""MCP `x402.policy_check` — unpaid PaymentRequired and paid path (mocked settle)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.types import CallToolResult
from x402.http import decode_payment_required_header, encode_payment_required_header
from x402.mcp.constants import MCP_PAYMENT_META_KEY
from x402.schemas import PaymentRequired, PaymentRequirements

from app import commerce, mcp_x402_payment, policy_check, x402_services
from app.config import settings


def _merchant_inspected_header() -> str:
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x2222222222222222222222222222222222222222",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="5000",
        max_timeout_seconds=300,
        extra={},
    )
    return encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="inspected")
    )


def _payment_ctx(payment: dict[str, Any]) -> SimpleNamespace:
    meta = SimpleNamespace(model_extra={MCP_PAYMENT_META_KEY: payment})
    request_context = SimpleNamespace(meta=meta)
    return SimpleNamespace(request_context=request_context)


@pytest.fixture
def policy_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "policy_check_enabled", True)
    assert settings.x402_pay_to_address


@pytest.mark.asyncio
async def test_policy_check_mcp_feature_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "policy_check_enabled", False)
    from app import mcp_server

    out = await mcp_server.policy_check_tool(
        payment_required_header=_merchant_inspected_header(),
        policy="{}",
        request_digest=None,
        idempotency_key=None,
        agent_id="a",
        ctx=None,
    )
    assert isinstance(out, CallToolResult)
    assert out.isError
    payload = out.content[0].text if out.content else ""
    assert "feature_disabled" in payload


@pytest.mark.asyncio
async def test_policy_check_mcp_unpaid_is_payment_required(policy_on: None) -> None:
    from app import mcp_server

    out = await mcp_server.policy_check_tool(
        payment_required_header=_merchant_inspected_header(),
        policy="{}",
        request_digest=None,
        idempotency_key=None,
        agent_id="mcp-pc-unpaid",
        ctx=None,
    )
    assert isinstance(out, CallToolResult)
    assert out.isError
    assert out.structuredContent
    assert out.structuredContent.get("x402Version") == 2


@pytest.mark.asyncio
async def test_policy_check_mcp_paid_success_mocked_settle(
    policy_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import mcp_server
    from app.commerce_payment import clear_commerce_challenges

    clear_commerce_challenges()
    policy_check.clear_idempotency_test()

    built = x402_services.build_policy_check_mcp_requirements("mcp-pc-paid")
    pr = decode_payment_required_header(built["payment_required_header"])
    accept = pr.accepts[0]
    payment = {
        "x402Version": 2,
        "payload": {"signature": "0xsig", "authorization": {}},
        "accepted": accept.model_dump(by_alias=True, exclude_none=True),
    }
    ctx = _payment_ctx(payment)

    async def fake_verify(_payment: dict[str, Any], _challenge: Any) -> dict[str, Any]:
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {
                "success": True,
                "transaction": "0xmcp123",
                "payer": "0xpayer00000000000000000000000000000001",
            },
        }

    monkeypatch.setattr(mcp_x402_payment, "verify_and_settle_mcp_payload", fake_verify)
    store = commerce.InMemoryQuotaStore()
    monkeypatch.setattr(mcp_server, "quota_store", store)

    raw = await mcp_server.policy_check_tool(
        payment_required_header=_merchant_inspected_header(),
        policy='{"allowed_networks":["eip155:84532"],"max_amount_atomic":"10000000"}',
        request_digest=None,
        idempotency_key=None,
        agent_id="mcp-pc-paid",
        ctx=ctx,
    )
    if isinstance(raw, CallToolResult):
        outer = json.loads(raw.content[0].text)
    else:
        outer = json.loads(raw)
    assert outer.get("data", {}).get("verdict") == "pass"
    assert outer.get("data", {}).get("own_service_settlement", {}).get("transaction") == "0xmcp123"
