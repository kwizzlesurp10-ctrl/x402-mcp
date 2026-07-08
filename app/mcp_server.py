"""FastMCP tool registrations for x402 micropayments."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.commerce import QuotaExceededError, quota_store
from app.config import settings
from app.models import (
    BuildSellerRequirementsInput,
    DiscoverServicesInput,
    GetPaymentRequirementsInput,
    PayAndFetchInput,
    ToolResponse,
    VerifyPaymentInput,
)
from app import x402_services

mcp = FastMCP(
    "x402-micropayments",
    instructions=(
        "MCP server for x402 HTTP micropayments. Discover paid services, "
        "probe 402 payment requirements, pay-and-fetch protected resources, "
        "build/verify seller payment configs, and upgrade to Pro via x402. "
        "Commerce meta included on every response."
    ),
)


async def _execute_tool(
    agent_id: str | None,
    work: Callable[[str], Awaitable[dict[str, Any]]],
) -> str:
    """Preemptive quota enforcement, then execute work, then attach meta."""
    resolved = quota_store.resolve_agent_id(agent_id)
    try:
        snapshot = quota_store.consume_quota(resolved)
    except QuotaExceededError as exc:
        return json.dumps({"error": exc.detail, "data": None, "meta": None}, indent=2)

    data = await work(resolved)
    payload = ToolResponse(data=data, meta=quota_store.build_meta(snapshot))
    return json.dumps(payload.model_dump(), indent=2)


@mcp.tool()
async def discover_services(
    query: str | None = None,
    limit: int = 20,
    max_price_usdc: float | None = None,
    agent_id: str | None = None,
) -> str:
    """Discover x402 Bazaar paid HTTP services via x402 HTTPFacilitatorClient."""
    params = DiscoverServicesInput(
        query=query, limit=limit, max_price_usdc=max_price_usdc
    )
    return await _execute_tool(
        agent_id, lambda _: x402_services.discover_services(params)
    )


@mcp.tool()
async def get_payment_requirements(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    agent_id: str | None = None,
) -> str:
    """Probe a URL for x402 payment requirements using x402HTTPClient SDK."""
    params = GetPaymentRequirementsInput(
        url=url, method=method, headers=headers or {}
    )
    return await _execute_tool(
        agent_id, lambda _: x402_services.get_payment_requirements(params)
    )


@mcp.tool()
async def pay_and_fetch(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
    preferred_network: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Pay via x402HttpxClient and fetch a protected HTTP resource."""
    params = PayAndFetchInput(
        url=url,
        method=method,
        headers=headers or {},
        body=body,
        preferred_network=preferred_network,
    )
    return await _execute_tool(agent_id, lambda _: x402_services.pay_and_fetch(params))


@mcp.tool()
async def build_seller_requirements(
    network: str = "eip155:84532",
    pay_to: str | None = None,
    price: str = "$0.01",
    scheme: str = "exact",
    description: str = "Paid MCP-backed API access",
    agent_id: str | None = None,
) -> str:
    """Build seller-side x402 payment requirements via x402ResourceServer."""
    params = BuildSellerRequirementsInput(
        network=network,
        pay_to=pay_to,
        price=price,
        scheme=scheme,
        description=description,
    )
    return await _execute_tool(
        agent_id,
        lambda _: _sync_result(x402_services.build_seller_requirements(params)),
    )


@mcp.tool()
async def verify_payment_payload(
    payment_signature: str,
    payment_required: str,
    agent_id: str | None = None,
) -> str:
    """Verify PAYMENT-SIGNATURE via x402ResourceServer + facilitator."""
    params = VerifyPaymentInput(
        payment_signature=payment_signature,
        payment_required=payment_required,
    )
    return await _execute_tool(
        agent_id, lambda _: x402_services.verify_payment_payload(params)
    )


@mcp.tool()
async def get_supported_networks(agent_id: str | None = None) -> str:
    """List networks, facilitators, and v2 headers via x402 SDK."""
    return await _execute_tool(
        agent_id,
        lambda _: _sync_result(x402_services.get_supported_networks().model_dump()),
    )


@mcp.tool()
async def get_pro_upgrade_requirements(agent_id: str | None = None) -> str:
    """Build x402 payment requirements to purchase Pro tier (revenue collection)."""
    return await _execute_tool(
        agent_id,
        lambda resolved: _sync_result(
            x402_services.build_pro_upgrade_requirements(resolved)
        ),
    )


@mcp.tool()
async def activate_pro_tier(
    payment_signature: str,
    payment_required: str,
    agent_id: str | None = None,
) -> str:
    """Verify pro-tier x402 payment and unlock Pro quota limits."""
    return await _execute_tool(
        agent_id,
        lambda resolved: x402_services.activate_pro_tier(
            payment_signature, payment_required, resolved
        ),
    )


@mcp.tool()
async def get_tool_credits_requirements(
    credits: int | None = None,
    agent_id: str | None = None,
) -> str:
    """Build x402 payment requirements to purchase per-use MCP tool credits."""
    pack = credits or settings.tool_credit_pack_size

    return await _execute_tool(
        agent_id,
        lambda resolved: _sync_result(
            x402_services.build_tool_credits_requirements(resolved, pack)
        ),
    )


@mcp.tool()
async def purchase_tool_credits(
    payment_signature: str,
    payment_required: str,
    credits: int | None = None,
    agent_id: str | None = None,
) -> str:
    """Verify x402 payment and add per-use tool credits (per-call revenue path)."""
    pack = credits or settings.tool_credit_pack_size

    return await _execute_tool(
        agent_id,
        lambda resolved: x402_services.purchase_tool_credits(
            payment_signature, payment_required, resolved, pack
        ),
    )


async def _sync_result(data: dict[str, Any]) -> dict[str, Any]:
    return data