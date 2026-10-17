"""US City Network MCP packaging — thin tools over existing HTTP products."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app import mcp_server
from app.city_compliance import mcp_tools as city_mcp
from app.city_compliance import registry
from app.config import settings
from app.tools_registry import EXPECTED_TOOL_NAMES, TOOL_SPECS
from x402.mcp.constants import MCP_PAYMENT_META_KEY


@pytest.mark.asyncio
async def test_list_us_cities_catalog_shape() -> None:
    data = await city_mcp.list_us_cities()
    assert data["network"] == "us-city-open-data-compliance"
    assert data["city_count"] >= 1
    assert "mn" in {c["code"] for c in data["cities"]}
    assert "golden_path" in data
    assert "list_us_cities" in data["golden_path"]["1_catalog"]
    assert data["cities"][0]["paid_url"].endswith("/property-check")
    assert data["cities"][0]["sample_url"].endswith("/sample")


@pytest.mark.asyncio
async def test_list_us_cities_mcp_wrapper() -> None:
    raw = await mcp_server.list_us_cities(agent_id="city-catalog-agent")
    payload = json.loads(raw)
    assert payload["meta"]["agent_id"]
    assert payload["data"]["network"] == "us-city-open-data-compliance"
    assert payload["data"]["city_count"] == len(registry.list_cities())


@pytest.mark.asyncio
async def test_get_us_city_property_sample_unknown_city() -> None:
    data = await city_mcp.get_us_city_property_sample("not-a-city")
    assert data["error"] == "unknown_city"
    assert "mn" in data["known"]


@pytest.mark.asyncio
async def test_get_us_city_property_sample_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_check(address: str) -> dict[str, Any]:
        return {"address": address, "compliance_verdict": "sample_ok", "city": "mn"}

    mod = registry.get_city("mn")
    monkeypatch.setattr(mod, "check_property", fake_check)

    data = await city_mcp.get_us_city_property_sample("mn")
    assert data["sample"] is True
    assert data["city"] == "mn"
    assert data["report"]["compliance_verdict"] == "sample_ok"
    assert data["next"]["action"] == "city.check"
    assert data["next"]["mcp_payment_meta"] == MCP_PAYMENT_META_KEY


@pytest.mark.asyncio
async def test_get_us_city_property_sample_mcp_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check(address: str) -> dict[str, Any]:
        return {"address": address, "ok": True}

    monkeypatch.setattr(registry.get_city("sea"), "check_property", fake_check)
    raw = await mcp_server.get_us_city_property_sample(
        city_code="sea", agent_id="city-sample-agent"
    )
    payload = json.loads(raw)
    assert payload["data"]["sample"] is True
    assert payload["data"]["city"] == "sea"
    assert "meta" in payload


@pytest.mark.asyncio
async def test_check_us_city_property_invalid_address() -> None:
    data = await city_mcp.check_us_city_property("mn", "   ")
    assert data["error"] == "invalid_address"


@pytest.mark.asyncio
async def test_check_us_city_property_seller_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check(address: str) -> dict[str, Any]:
        return {"address": address, "compliance_verdict": "paid_ok"}

    monkeypatch.setattr(registry.get_city("chi"), "check_property", fake_check)

    data = await city_mcp.check_us_city_property("chi", "121 N LaSalle St")
    assert data["paid"] is True
    assert data["city"] == "chi"
    assert data["report"]["compliance_verdict"] == "paid_ok"


@pytest.mark.asyncio
async def test_check_us_city_property_mcp_wrapper_unpaid() -> None:
    result = await mcp_server.mcp._tool_manager.call_tool(
        "city.check",
        {"city_code": "nyc", "address": "1 Centre St", "agent_id": "city-paid-agent"},
        convert_result=True,
    )
    assert result.isError is True
    assert result.structuredContent
    assert result.structuredContent.get("x402Version") == 2


def test_city_tools_in_registry() -> None:
    for name in (
        "city.list",
        "city.sample",
        "city.check",
    ):
        assert name in EXPECTED_TOOL_NAMES


def test_city_check_description_advertises_price() -> None:
    spec = next(s for s in TOOL_SPECS if s["name"] == "city.check")
    assert "Price: $0.01 per call (x402, USDC on Base/Solana/Arbitrum)." in spec["description"]
    assert spec["tier"] == "paid"
