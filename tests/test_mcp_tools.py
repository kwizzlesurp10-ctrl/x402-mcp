"""MCP tool layer — preemptive quota, wrapper 429, direct invocation."""

import json

import pytest

from app import mcp_server
from app.commerce import InMemoryQuotaStore, quota_store
from app.config import settings
from app.manifest import build_mcp_manifest
from app.tools_registry import EXPECTED_TOOL_NAMES, TOOL_COUNT

# Back-compat alias for docker/readme evidence tests
EXPECTED_TOOLS = EXPECTED_TOOL_NAMES


def test_all_tools_registered() -> None:
    tool_names = {t.name for t in mcp_server.mcp._tool_manager._tools.values()}
    assert tool_names == EXPECTED_TOOL_NAMES
    assert len(tool_names) == TOOL_COUNT


def test_manifest_tools_match_registry() -> None:
    manifest_names = {t["name"] for t in build_mcp_manifest()["tools"]}
    assert manifest_names == EXPECTED_TOOL_NAMES


@pytest.mark.asyncio
async def test_get_supported_networks_tool_response_shape() -> None:
    raw = await mcp_server.get_supported_networks(agent_id="smoke-agent-1")
    payload = json.loads(raw)

    assert "data" in payload
    assert "meta" in payload
    meta = payload["meta"]
    assert meta["tier"] == "free"
    assert "quota_remaining" in meta
    assert meta["upgrade_url"]

    data = payload["data"]
    assert data["protocol_version"] == "v2"
    assert "PAYMENT-REQUIRED" in data["headers"]
    assert any(n["id"].startswith("eip155:") for n in data["networks"])


@pytest.mark.asyncio
async def test_rate_limit_through_mcp_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 must surface through MCP tool wrapper, not only InMemoryQuotaStore."""
    tight = InMemoryQuotaStore()
    monkeypatch.setattr(mcp_server, "quota_store", tight)
    monkeypatch.setattr(settings, "free_tier_rate_limit_per_min", 2)

    agent = "mcp-rate-limit-agent"
    await mcp_server.get_supported_networks(agent_id=agent)
    await mcp_server.get_supported_networks(agent_id=agent)

    raw = await mcp_server.get_supported_networks(agent_id=agent)
    payload = json.loads(raw)

    assert payload.get("error") is not None
    assert payload["error"]["error"] == "rate_limit_exceeded"
    assert payload["data"] is None
    assert "retry_after" in payload["error"]


@pytest.mark.asyncio
async def test_quota_consumed_before_work_on_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preemptive enforcement: expensive work must not run when quota exceeded."""
    calls = {"discover": 0}
    original = mcp_server.x402_services.discover_services

    async def spy_discover(params):
        calls["discover"] += 1
        return await original(params)

    monkeypatch.setattr(mcp_server.x402_services, "discover_services", spy_discover)

    tight = InMemoryQuotaStore()
    monkeypatch.setattr(mcp_server, "quota_store", tight)
    monkeypatch.setattr(settings, "free_tier_rate_limit_per_min", 1)

    agent = "preempt-agent"
    await mcp_server.discover_services(limit=1, agent_id=agent)
    await mcp_server.discover_services(limit=1, agent_id=agent)

    assert calls["discover"] == 1


@pytest.mark.asyncio
async def test_build_seller_requirements_missing_config() -> None:
    with pytest.raises(ValueError, match="pay_to address required"):
        await mcp_server.build_seller_requirements(agent_id="seller-skip-agent")


@pytest.mark.asyncio
async def test_pay_and_fetch_missing_wallet() -> None:
    with pytest.raises(ValueError, match="EVM_PRIVATE_KEY"):
        await mcp_server.pay_and_fetch(
            url="https://example.com/paid",
            agent_id="pay-skip-agent",
        )


@pytest.mark.asyncio
async def test_get_payment_requirements_tool_invocable(probe_402_url: str) -> None:
    raw = await mcp_server.get_payment_requirements(
        url=probe_402_url,
        agent_id="probe-smoke",
    )
    payload = json.loads(raw)
    assert payload["data"]["status_code"] == 402
    assert "x402HTTPClient.get_payment_required_response" in payload["data"]["sdk"]
    assert "meta" in payload


@pytest.mark.asyncio
async def test_pro_upgrade_agent_id_matches_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    """agent_id=None must resolve once — meta and data must share the same id."""
    monkeypatch.setattr(settings, "x402_pay_to_address", "0xTestPayTo00000000000000000000000001")

    raw = await mcp_server.get_pro_upgrade_requirements(agent_id=None)
    payload = json.loads(raw)

    assert payload["meta"]["agent_id"] == payload["data"]["agent_id"]


@pytest.mark.asyncio
async def test_tool_credits_requirements_agent_id_matches_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", "0xTestPayTo00000000000000000000000001")

    raw = await mcp_server.get_tool_credits_requirements(agent_id=None, credits=50)
    payload = json.loads(raw)

    assert payload["meta"]["agent_id"] == payload["data"]["agent_id"]
    assert payload["data"]["credits"] == 50
    assert payload["data"]["purpose"] == "tool_credits"


@pytest.mark.asyncio
async def test_activate_pro_tier_through_mcp_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """activate_pro_tier must use single resolved agent_id via _execute_tool."""
    store = InMemoryQuotaStore()
    monkeypatch.setattr(mcp_server, "quota_store", store)

    async def fake_activate(
        payment_signature: str,
        payment_required: str,
        agent_id: str,
    ) -> dict:
        store.activate_pro_tier(agent_id)
        return {
            "activated": True,
            "agent_id": agent_id,
            "tier": "pro",
            "pro_quota": settings.pro_tier_monthly_quota,
            "payment_settled": True,
            "verification": {"is_valid": True, "sdk": "mock"},
        }

    monkeypatch.setattr(mcp_server.x402_services, "activate_pro_tier", fake_activate)

    raw = await mcp_server.activate_pro_tier(
        payment_signature="sig",
        payment_required="req",
        agent_id=None,
    )
    payload = json.loads(raw)

    assert payload["meta"]["agent_id"] == payload["data"]["agent_id"]
    assert payload["data"]["tier"] == "pro"
    assert store.get_tier(payload["meta"]["agent_id"]) == "pro"


@pytest.mark.asyncio
async def test_purchase_tool_credits_through_mcp_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """purchase_tool_credits must use single resolved agent_id via _execute_tool."""
    store = InMemoryQuotaStore()
    monkeypatch.setattr(mcp_server, "quota_store", store)

    async def fake_purchase(
        payment_signature: str,
        payment_required: str,
        agent_id: str,
        credits: int,
    ) -> dict:
        balance = store.add_credits(agent_id, credits)
        return {
            "credited": True,
            "agent_id": agent_id,
            "credits_purchased": credits,
            "tool_credits_remaining": balance,
            "tier": store.get_tier(agent_id),
            "payment_settled": True,
            "verification": {"is_valid": True, "sdk": "mock"},
        }

    monkeypatch.setattr(mcp_server.x402_services, "purchase_tool_credits", fake_purchase)

    raw = await mcp_server.purchase_tool_credits(
        payment_signature="sig",
        payment_required="req",
        credits=25,
        agent_id=None,
    )
    payload = json.loads(raw)

    assert payload["meta"]["agent_id"] == payload["data"]["agent_id"]
    assert payload["data"]["credits_purchased"] == 25
    assert payload["data"]["tool_credits_remaining"] == 25
    assert store.get_credits(payload["meta"]["agent_id"]) == 25