"""MCP stdio transport — drives tools through real MCP protocol, not direct imports."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _python_exe() -> Path:
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)
    return python


def _stdio_server_params(env: dict[str, str] | None = None):
    pytest.importorskip("mcp")
    import os

    from mcp import StdioServerParameters

    merged_env = {**os.environ, **(env or {})}
    return StdioServerParameters(
        command=str(_python_exe()),
        args=[str(ROOT / "run_stdio.py")],
        cwd=str(ROOT),
        env=merged_env,
    )


async def _call_stdio_tool(
    tool_name: str,
    arguments: dict,
    *,
    env: dict[str, str] | None = None,
    session=None,
) -> dict:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    if session is not None:
        result = await session.call_tool(tool_name, arguments)
        assert not result.isError
        assert result.content
        return json.loads(result.content[0].text)

    async with stdio_client(_stdio_server_params(env)) as (read, write):
        async with ClientSession(read, write) as new_session:
            await new_session.initialize()
            result = await new_session.call_tool(tool_name, arguments)

    assert not result.isError
    assert result.content
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_stdio_get_supported_networks() -> None:
    payload = await _call_stdio_tool(
        "get_supported_networks",
        {"agent_id": "stdio-smoke-agent"},
    )

    assert "data" in payload
    assert "meta" in payload
    assert payload["meta"]["tier"] == "free"
    assert "PAYMENT-REQUIRED" in payload["data"]["headers"]


@pytest.mark.asyncio
async def test_stdio_get_payment_requirements(probe_402_url: str) -> None:
    payload = await _call_stdio_tool(
        "get_payment_requirements",
        {
            "url": probe_402_url,
            "agent_id": "stdio-probe-agent",
        },
    )

    assert payload["data"]["status_code"] == 402
    assert "x402HTTPClient.get_payment_required_response" in payload["data"]["sdk"]
    assert "meta" in payload


@pytest.mark.asyncio
async def test_stdio_get_pro_upgrade_requirements() -> None:
    payload = await _call_stdio_tool(
        "get_pro_upgrade_requirements",
        {},
        env={
            "X402_PAY_TO_ADDRESS": "0xTestPayTo00000000000000000000000001",
            # Pin testnet: local CDP creds would resolve revenue to mainnet.
            "REVENUE_NETWORK": "eip155:84532",
        },
    )

    assert payload["meta"]["agent_id"] == payload["data"]["agent_id"]
    assert payload["data"]["purpose"] == "pro_tier_upgrade"


@pytest.mark.asyncio
async def test_stdio_get_tool_credits_requirements() -> None:
    payload = await _call_stdio_tool(
        "get_tool_credits_requirements",
        {"credits": 25},
        env={
            "X402_PAY_TO_ADDRESS": "0xTestPayTo00000000000000000000000001",
            "REVENUE_NETWORK": "eip155:84532",
        },
    )

    assert payload["meta"]["agent_id"] == payload["data"]["agent_id"]
    assert payload["data"]["credits"] == 25


@pytest.mark.asyncio
async def test_stdio_quota_exceeded_includes_upgrade_tools() -> None:
    """Stdio transport must surface quota 429 with upgrade/credits tool hints."""
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    tight_env = {
        "FREE_TIER_MONTHLY_QUOTA": "3",
        "FREE_TIER_RATE_LIMIT_PER_MIN": "1000",
    }
    agent = "stdio-quota-exceeded-agent"

    async with stdio_client(_stdio_server_params(tight_env)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for _ in range(3):
                await _call_stdio_tool(
                    "get_supported_networks",
                    {"agent_id": agent},
                    session=session,
                )
            payload = await _call_stdio_tool(
                "get_supported_networks",
                {"agent_id": agent},
                session=session,
            )

    assert payload.get("error") is not None
    assert payload["error"]["error"] == "monthly_quota_exceeded"
    assert payload["error"]["purchase_credits_tool"] == "purchase_tool_credits"
    assert payload["error"]["credits_payment_tool"] == "get_tool_credits_requirements"