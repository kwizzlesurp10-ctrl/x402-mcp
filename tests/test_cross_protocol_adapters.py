"""Tests for Olas Mech and Nevermined cross-protocol adapters."""

from __future__ import annotations

import pytest

from app.adapters.olas_mech_adapter import OlasMechAdapter
from app.adapters.nevermined_adapter import NeverminedAdapter


@pytest.mark.asyncio
async def test_olas_mech_adapter_supported_tools() -> None:
    tools = OlasMechAdapter.get_supported_tools()
    assert len(tools) >= 3
    tool_names = {t["name"] for t in tools}
    assert "us-rental-diligence" in tool_names
    assert "base-tx-decision" in tool_names


@pytest.mark.asyncio
async def test_olas_mech_adapter_executes_diligence() -> None:
    req = {
        "tool": "us-rental-diligence",
        "task_id": "0x1234567890abcdef",
        "params": {
            "properties": [
                {"city_code": "mn", "address": "1700 Penn Ave N"},
            ],
            "include_base_pulse_context": False,
        },
    }
    resp = await OlasMechAdapter.execute_task(req)
    assert resp["status"] == "success"
    assert resp["tool"] == "us-rental-diligence"
    assert resp["task_id"] == "0x1234567890abcdef"
    assert resp["deliverable_hash"].startswith("0x")
    assert resp["cost_usdc"] == 1.50
    assert "result" in resp
    assert resp["result"]["payment_settled"] is True


@pytest.mark.asyncio
async def test_olas_mech_adapter_unsupported_tool() -> None:
    req = {"tool": "invalid-nonexistent-tool"}
    resp = await OlasMechAdapter.execute_task(req)
    assert resp["status"] == "error"
    assert "unsupported_tool" in resp["error"]


@pytest.mark.asyncio
async def test_nevermined_adapter_plans() -> None:
    plans = NeverminedAdapter.get_plans()
    assert len(plans) >= 2
    plan_ids = {p["plan_id"] for p in plans}
    assert "plan-us-rental-diligence" in plan_ids


@pytest.mark.asyncio
async def test_nevermined_adapter_auth_check() -> None:
    # Unauthenticated
    status, res = await NeverminedAdapter.process_task("us-rental-diligence", {}, {})
    assert status == 402
    assert res["error"] == "payment_required"

    # Authenticated
    headers = {"authorization": "Bearer sample_nvm_subscriber_jwt_token"}
    status, res = await NeverminedAdapter.process_task(
        "us-rental-diligence",
        {"properties": [{"city_code": "mn", "address": "1700 Penn Ave N"}]},
        headers,
    )
    assert status == 200
    assert res["payment_settled"] is True
    assert "nvm_settlement" in res
