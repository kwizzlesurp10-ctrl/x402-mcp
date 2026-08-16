"""US City Network MCP packaging — thin tools over existing HTTP products."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app import mcp_server
from app.city_compliance import mcp_tools as city_mcp
from app.city_compliance import registry
from app.config import settings
from app.tools_registry import EXPECTED_TOOL_NAMES


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
    assert data["next"]["action"] == "check_us_city_property"
    assert "EVM_PRIVATE_KEY" in data["next"]["requires_env"]


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
async def test_check_us_city_property_no_wallet_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "evm_private_key", None)

    async def fake_probe(params):  # noqa: ANN001
        return {
            "status_code": 402,
            "url": str(params.url),
            "sdk": "mock-probe",
            "payment_required": {"x402Version": 2},
        }

    monkeypatch.setattr(city_mcp.x402_services, "get_payment_requirements", fake_probe)

    data = await city_mcp.check_us_city_property("mn", "1700 Penn Ave N")
    assert data["paid"] is False
    assert data["reason"] == "buyer_wallet_not_configured"
    assert data["city"] == "mn"
    assert "address=" in data["paid_url"]
    assert data["payment_probe"]["status_code"] == 402
    assert data["mcp"]["tool"] == "check_us_city_property"
    assert "pay_and_fetch" in data["mcp"]["alternate_tool"]


@pytest.mark.asyncio
async def test_check_us_city_property_with_wallet_pay_and_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "evm_private_key", "0x" + "ab" * 32)

    async def fake_pay(params):  # noqa: ANN001
        return {
            "status_code": 200,
            "url": str(params.url),
            "body": {"compliance_verdict": "paid_ok"},
            "sdk": "mock-pay",
        }

    monkeypatch.setattr(city_mcp.x402_services, "pay_and_fetch", fake_pay)

    data = await city_mcp.check_us_city_property("chi", "121 N LaSalle St")
    assert data["paid"] is True
    assert data["city"] == "chi"
    assert data["result"]["body"]["compliance_verdict"] == "paid_ok"


@pytest.mark.asyncio
async def test_check_us_city_property_mcp_wrapper_no_wallet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "evm_private_key", None)

    async def fake_probe(params):  # noqa: ANN001
        return {"status_code": 402, "url": str(params.url)}

    monkeypatch.setattr(city_mcp.x402_services, "get_payment_requirements", fake_probe)

    raw = await mcp_server.check_us_city_property(
        city_code="nyc",
        address="1 Centre St",
        agent_id="city-paid-agent",
    )
    payload = json.loads(raw)
    assert payload["meta"]["agent_id"]
    assert payload["data"]["paid"] is False
    assert payload["data"]["city"] == "nyc"


def test_city_tools_in_registry() -> None:
    for name in (
        "list_us_cities",
        "get_us_city_property_sample",
        "check_us_city_property",
    ):
        assert name in EXPECTED_TOOL_NAMES
