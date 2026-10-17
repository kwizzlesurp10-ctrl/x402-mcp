"""MCP seller x402 payment wrapper (city.check)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app import mcp_server
from app.mcp_payments import build_city_check_payment_bundle, city_check_payment_wrapper
from x402.mcp.constants import MCP_PAYMENT_META_KEY


@pytest.mark.asyncio
async def test_city_check_unpaid_returns_payment_required() -> None:
    wrapper = city_check_payment_wrapper()
    tool = mcp_server.mcp._tool_manager._tools["city.check"]
    handler = tool.fn

    result = await handler(city_code="mn", address="1700 Penn Ave N")
    assert result.isError is True
    assert result.structuredContent is not None
    sc = result.structuredContent
    assert sc.get("x402Version") == 2
    assert sc.get("accepts")
    assert sc.get("resource")
    extensions = sc.get("extensions") or {}
    bazaar = extensions.get("bazaar") or {}
    info = (bazaar.get("info") or {}).get("input") or {}
    assert info.get("type") == "mcp"
    assert info.get("toolName") == "city.check"
    assert info.get("example") == {"city_code": "mn", "address": "1700 Penn Ave N"}


def test_city_check_bazaar_bundle_has_accepts() -> None:
    accepts, resource, extensions = build_city_check_payment_bundle()
    assert len(accepts) >= 1
    assert resource.url.endswith("/mcp/mcp")
    assert "bazaar" in extensions


@pytest.mark.asyncio
async def test_city_check_paid_execution_via_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.city_compliance import registry

    async def fake_check(address: str) -> dict[str, Any]:
        return {"address": address, "compliance_verdict": "mcp_paid_ok"}

    monkeypatch.setattr(registry.get_city("mn"), "check_property", fake_check)

    tool = mcp_server.mcp._tool_manager._tools["city.check"]
    handler = tool.fn

    # Minimal payment payload — verify/settle mocked at resource server layer.
    from app.mcp_payments import get_mcp_resource_server

    server = get_mcp_resource_server()

    async def fake_verify(payload, requirements):  # noqa: ANN001
        from x402.schemas.responses import VerifyResponse

        return VerifyResponse(is_valid=True)

    async def fake_settle(payload, requirements):  # noqa: ANN001
        from x402.schemas.responses import SettleResponse

        return SettleResponse(
            success=True,
            transaction="0xmcp_test_tx",
            network=requirements.network,
            payer="0xbuyer",
        )

    monkeypatch.setattr(server, "verify_payment", fake_verify)
    monkeypatch.setattr(server, "settle_payment", fake_settle)

    class _Meta:
        model_extra = {
            MCP_PAYMENT_META_KEY: {
                "x402Version": 2,
                "scheme": "exact",
                "network": "eip155:84532",
                "payload": {},
                "accepted": {},
            }
        }

    class _RequestContext:
        meta = _Meta()

    class _Ctx:
        request_context = _RequestContext()

    # Build a valid-looking payload using the same accepts the wrapper uses.
    accepts, _, _ = build_city_check_payment_bundle()
    req = accepts[0]
    payment_body = {
        "x402Version": 2,
        "scheme": req.scheme,
        "network": req.network,
        "payload": {"signature": "0x" + "00" * 32},
        "accepted": req.model_dump(by_alias=True, exclude_none=True),
    }
    _Meta.model_extra[MCP_PAYMENT_META_KEY] = payment_body

    result = await handler(
        city_code="mn",
        address="1700 Penn Ave N",
        agent_id="mcp-pay-agent",
        ctx=_Ctx(),
    )
    assert result.isError is False
    payload = json.loads(result.content[0].text)
    assert payload["data"]["report"]["compliance_verdict"] == "mcp_paid_ok"
    from x402.mcp.constants import MCP_PAYMENT_RESPONSE_META_KEY

    assert MCP_PAYMENT_RESPONSE_META_KEY in (result.meta or {})
