"""FastMCP tool registrations for x402 micropayments."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

from app import stripe_payments, x402_services
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
from app.ops_events import emit_tool_event
from app.swarm import orchestrator as swarm_orchestrator

Desc = Annotated

# Smithery quality: clients treat these as routing hints (read vs spend).
READONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
READONLY_EXTERNAL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
WRITE_PAYMENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)
WRITE_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

INSTRUCTIONS = (
    "x402 micropayments MCP (USDC on Base). Route by domain: "
    "x402.* buyer/seller HTTP 402, commerce.* quota/credits/Stripe, "
    "swarm.* composite research resale, pulse.base settlement timing, "
    "ops.metrics host health, city.* US open-data property compliance. "
    "Buyer path: x402.discover → x402.probe → x402.pay_and_fetch. "
    "City path: city.list → city.sample → city.check. "
    "Pro quota: commerce.pro_requirements → pay → commerce.activate_pro. "
    "Credits: commerce.credits_requirements → pay → commerce.purchase_credits. "
    "Fiat alternative: commerce.stripe_checkout. "
    "Public seller hosts have no spend key — probe tools still work; "
    "pay-and-fetch needs EVM_PRIVATE_KEY. Every tool response includes commerce meta."
)

_SMITHERY_HOSTS = (
    "server.smithery.ai",
    "x402-mcp--kwizzlesurp10.run.tools",
    "x402-mcp.onrender.com",
)
_SMITHERY_ORIGINS = (
    "https://smithery.ai",
    "https://www.smithery.ai",
    "https://server.smithery.ai",
    "https://claude.ai",
    "https://www.claude.ai",
    "https://cursor.com",
    "https://www.cursor.com",
)


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _transport_security() -> TransportSecuritySettings:
    """Allow this deployment's own hostname through DNS-rebinding protection.

    FastMCP defaults to allowing localhost only, so on a public host every
    Streamable HTTP request is rejected with 421 "Invalid Host header" and the
    server is unreachable to any remote MCP client — which is most of the point
    of deploying it. The protection stays ON; the deployment's own host is added
    to the allowlist rather than the check being switched off.

    Smithery's gateway and playground send Host/Origin of smithery.ai /
    *.run.tools. Those must be allowlisted or initialize/tools/list 403/421.
    """
    allowed = ["127.0.0.1:*", "localhost:*", "[::1]:*", "testserver", "testserver:*"]
    origins = [
        "http://localhost:*",
        "http://127.0.0.1:*",
        *_SMITHERY_ORIGINS,
    ]
    public = urlparse(settings.public_base_url).netloc
    if public and not public.startswith(("localhost", "127.0.0.1")):
        host = public.split(":")[0]
        allowed.append(host)
        allowed.append(f"{host}:*")
        origins.append(f"https://{host}")
        origins.append(f"https://{host}:*")
    for host in _SMITHERY_HOSTS:
        if host not in allowed:
            allowed.append(host)
            allowed.append(f"{host}:*")
    for host in _csv(getattr(settings, "mcp_allowed_hosts", "") or ""):
        if host not in allowed:
            allowed.append(host)
            allowed.append(f"{host}:*")
    for origin in _csv(getattr(settings, "mcp_allowed_origins", "") or ""):
        if origin not in origins:
            origins.append(origin)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed,
        allowed_origins=origins,
    )


mcp = FastMCP(
    "x402-micropayments",
    instructions=INSTRUCTIONS,
    transport_security=_transport_security(),
    # JSON bodies (not SSE) so Smithery Connect and other HTTP gateways can
    # parse initialize/tools/list. Stateless so proxies that drop
    # Mcp-Session-Id still work for a single request.
    json_response=True,
    stateless_http=True,
)


async def _execute_tool(
    tool_name: str,
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
    meta = quota_store.build_meta(snapshot)
    emit_tool_event(tool_name, resolved, meta.model_dump())
    payload = ToolResponse(data=data, meta=meta)
    return json.dumps(payload.model_dump(), indent=2)


@mcp.tool(
    name="x402.agent_card",
    title="A2A Agent ID Card",
    description=(
        "Return the A2A Protocol v1.0 Agent ID Card and MCP server card. "
        "Optional target_id filters to a skill id, name, or tag."
    ),
    annotations=READONLY,
)
async def get_agent_card(
    target_id: Desc[
        str | None,
        Field(
            description=(
                "Optional skill ID, tool name, or tag to inspect. "
                "Omit for the full server agent card."
            ),
        ),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(description="Optional calling agent identifier for quota tracking."),
    ] = None,
) -> str:
    from app.agent_surface import agent_card, mcp_server_card

    def _build_card(resolved_agent_id: str) -> dict[str, Any]:
        card = agent_card()
        server_meta = mcp_server_card()
        if target_id:
            matching_skills = [
                s
                for s in card.get("skills", [])
                if s.get("id") == target_id
                or target_id in s.get("tags", [])
                or target_id == s.get("name")
            ]
            if matching_skills:
                return {
                    "agent_id": resolved_agent_id,
                    "target_id": target_id,
                    "skills": matching_skills,
                    "provider": card.get("provider"),
                    "securitySchemes": card.get("securitySchemes"),
                    "serverInfo": server_meta.get("serverInfo"),
                }
        return {
            "agent_id": resolved_agent_id,
            "card": card,
            "server_card": server_meta,
            "tools_count": len(card.get("skills", [])),
        }

    return await _execute_tool(
        "x402.agent_card",
        agent_id,
        lambda resolved: _sync_result(_build_card(resolved)),
    )


@mcp.tool(
    name="x402.discover",
    title="Discover x402 services",
    description=(
        "Discover paid HTTP APIs in the x402 Bazaar via the facilitator catalog. "
        "Call this first to find a resource URL, then x402.probe and x402.pay_and_fetch."
    ),
    annotations=READONLY_EXTERNAL,
)
async def discover_services(
    query: Desc[
        str | None,
        Field(
            description=(
                "Optional Bazaar search substring. Example: 'weather' or 'image'. "
                "Omit to list recent paid HTTP services."
            )
        ),
    ] = None,
    limit: Desc[
        int,
        Field(
            description="Maximum number of catalog entries to return. Default 20. Range 1–100."
        ),
    ] = 20,
    max_price_usdc: Desc[
        float | None,
        Field(
            description=(
                "Optional USDC price ceiling. Example: 0.05. Omit to include any listed price."
            )
        ),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(
            description=(
                "Optional agent identity for quota accounting. Example: 'agent-42'. "
                "Omit to use the anonymous free-tier id."
            )
        ),
    ] = None,
) -> str:
    params = DiscoverServicesInput(
        query=query, limit=limit, max_price_usdc=max_price_usdc
    )
    return await _execute_tool(
        "x402.discover", agent_id, lambda _: x402_services.discover_services(params)
    )


@mcp.tool(
    name="x402.probe",
    title="Probe x402 payment requirements",
    description=(
        "Probe a URL for HTTP 402 PAYMENT-REQUIRED terms using the x402 client SDK. "
        "Use before x402.pay_and_fetch to inspect price, network, and payTo without spending."
    ),
    annotations=READONLY_EXTERNAL,
)
async def get_payment_requirements(
    url: Desc[
        str,
        Field(
            description=(
                "Absolute HTTP URL to probe. Example: "
                "'https://x402-mcp.onrender.com/us/mn/property-check?address=1700%20Penn%20Ave%20N'."
            )
        ),
    ],
    method: Desc[
        str,
        Field(description="HTTP method for the probe. Default GET. Example: 'GET' or 'POST'."),
    ] = "GET",
    headers: Desc[
        dict[str, str] | None,
        Field(
            description=(
                "Optional extra request headers as a string map. Example: "
                "{\"Accept\": \"application/json\"}. Omit if none."
            )
        ),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(
            description="Optional agent identity for quota accounting. Omit for the anonymous free-tier id."
        ),
    ] = None,
) -> str:
    params = GetPaymentRequirementsInput(
        url=url, method=method, headers=headers or {}
    )
    return await _execute_tool(
        "x402.probe",
        agent_id,
        lambda _: x402_services.get_payment_requirements(params),
    )


@mcp.tool(
    name="x402.pay_and_fetch",
    title="Pay and fetch x402 resource",
    description=(
        "Pay USDC via x402 and fetch a protected HTTP resource in one call. "
        "Requires EVM_PRIVATE_KEY on this host; otherwise use x402.probe for a no-spend 402."
    ),
    annotations=WRITE_PAYMENT,
)
async def pay_and_fetch(
    url: Desc[
        str,
        Field(description="Absolute paid HTTP URL to fetch after settling USDC."),
    ],
    method: Desc[
        str,
        Field(description="HTTP method for the paid request. Default GET."),
    ] = "GET",
    headers: Desc[
        dict[str, str] | None,
        Field(description="Optional extra request headers as a string map. Omit if none."),
    ] = None,
    body: Desc[
        str | None,
        Field(description="Optional raw request body for POST/PUT. Omit for GET."),
    ] = None,
    preferred_network: Desc[
        str | None,
        Field(
            description=(
                "Preferred CAIP-2 network. Example: 'eip155:8453' (Base mainnet). "
                "Omit to use the server default. Call x402.networks to list options."
            )
        ),
    ] = None,
    max_price_usdc: Desc[
        float | None,
        Field(
            description="Optional spend ceiling in USDC. Example: 0.10. Calls above this are blocked."
        ),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    params = PayAndFetchInput(
        url=url,
        method=method,
        headers=headers or {},
        body=body,
        preferred_network=preferred_network,
        max_price_usdc=max_price_usdc,
    )
    return await _execute_tool(
        "x402.pay_and_fetch", agent_id, lambda _: x402_services.pay_and_fetch(params)
    )


@mcp.tool(
    name="x402.build_seller",
    title="Build seller payment requirements",
    description=(
        "Build seller-side x402 payment requirements for your own HTTP resource. "
        "Pass resource_url plus discovery_* fields to catalog the endpoint in Bazaar."
    ),
    annotations=WRITE_IDEMPOTENT,
)
async def build_seller_requirements(
    network: Desc[
        str,
        Field(
            description="CAIP-2 settlement network. Default eip155:84532 (Base Sepolia). Mainnet: eip155:8453."
        ),
    ] = "eip155:84532",
    pay_to: Desc[
        str | None,
        Field(
            description="0x recipient for USDC. Example: '0x67ff…'. Omit to use X402_PAY_TO_ADDRESS."
        ),
    ] = None,
    price: Desc[
        str,
        Field(description="List price string. Default '$0.01'. Example: '$0.05'."),
    ] = "$0.01",
    scheme: Desc[
        str,
        Field(description="x402 payment scheme. Default 'exact'."),
    ] = "exact",
    description: Desc[
        str,
        Field(description="Human-readable description embedded in PAYMENT-REQUIRED."),
    ] = "Paid MCP-backed API access",
    resource_url: Desc[
        str | None,
        Field(
            description=(
                "Public URL of the paid resource. When set with discovery_* fields, "
                "Bazaar catalogs the endpoint after a settled payment."
            )
        ),
    ] = None,
    mime_type: Desc[
        str | None,
        Field(description="Resource MIME type. Default application/json."),
    ] = "application/json",
    discoverable: Desc[
        bool | None,
        Field(description="If true, embed the Bazaar discovery extension. Omit to use server default."),
    ] = None,
    discovery_method: Desc[
        str,
        Field(description="HTTP method advertised to Bazaar. Default GET."),
    ] = "GET",
    discovery_input_example: Desc[
        dict | None,
        Field(description="Optional example input object for Bazaar. Omit if none."),
    ] = None,
    discovery_output_example: Desc[
        dict | None,
        Field(description="Optional example output object for Bazaar. Omit if none."),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    params = BuildSellerRequirementsInput(
        network=network,
        pay_to=pay_to,
        price=price,
        scheme=scheme,
        description=description,
        resource_url=resource_url,
        mime_type=mime_type,
        discoverable=discoverable,
        discovery_method=discovery_method,
        discovery_input_example=discovery_input_example,
        discovery_output_example=discovery_output_example,
    )
    return await _execute_tool(
        "x402.build_seller",
        agent_id,
        lambda _: _sync_result(x402_services.build_seller_requirements(params)),
    )


@mcp.tool(
    name="x402.verify",
    title="Verify x402 payment signature",
    description=(
        "Verify an x402 PAYMENT-SIGNATURE against PAYMENT-REQUIRED terms via the facilitator. "
        "Call after a buyer presents a signature and before releasing paid content."
    ),
    annotations=WRITE_PAYMENT,
)
async def verify_payment_payload(
    payment_signature: Desc[
        str,
        Field(description="PAYMENT-SIGNATURE header value from the buyer."),
    ],
    payment_required: Desc[
        str,
        Field(description="PAYMENT-REQUIRED JSON/header the signature is meant to satisfy."),
    ],
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    params = VerifyPaymentInput(
        payment_signature=payment_signature,
        payment_required=payment_required,
    )
    return await _execute_tool(
        "x402.verify",
        agent_id,
        lambda _: x402_services.verify_payment_payload(params),
    )


@mcp.tool(
    name="x402.networks",
    title="List x402 networks",
    description=(
        "List supported settlement networks, facilitators, and x402 v2 header names. "
        "Call when choosing a preferred_network for x402.pay_and_fetch or x402.build_seller."
    ),
    annotations=READONLY,
)
async def get_supported_networks(
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    return await _execute_tool(
        "x402.networks",
        agent_id,
        lambda _: _sync_result(x402_services.get_supported_networks().model_dump()),
    )


@mcp.tool(
    name="commerce.pro_requirements",
    title="Build Pro-tier payment requirements",
    description=(
        "Build x402 payment requirements to purchase the Pro quota tier. "
        "Next: pay those terms, then commerce.activate_pro with the signature."
    ),
    annotations=READONLY_EXTERNAL,
)
async def get_pro_upgrade_requirements(
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity the Pro grant will attach to."),
    ] = None,
) -> str:
    return await _execute_tool(
        "commerce.pro_requirements",
        agent_id,
        lambda resolved: _sync_result(
            x402_services.build_pro_upgrade_requirements(resolved)
        ),
    )


@mcp.tool(
    name="commerce.activate_pro",
    title="Activate Pro tier",
    description=(
        "Verify a Pro-tier x402 payment and unlock Pro quota limits for the agent. "
        "Call after commerce.pro_requirements and a completed USDC payment."
    ),
    annotations=WRITE_PAYMENT,
)
async def activate_pro_tier(
    payment_signature: Desc[
        str,
        Field(description="PAYMENT-SIGNATURE from the Pro-tier USDC payment."),
    ],
    payment_required: Desc[
        str,
        Field(description="PAYMENT-REQUIRED JSON returned by commerce.pro_requirements."),
    ],
    agent_id: Desc[
        str | None,
        Field(description="Agent identity to grant Pro quota. Must match the requirements call."),
    ] = None,
) -> str:
    return await _execute_tool(
        "commerce.activate_pro",
        agent_id,
        lambda resolved: x402_services.activate_pro_tier(
            payment_signature, payment_required, resolved
        ),
    )


@mcp.tool(
    name="commerce.credits_requirements",
    title="Build tool-credit payment requirements",
    description=(
        "Build x402 payment requirements to buy a pack of per-use MCP tool credits. "
        "Next: pay those terms, then commerce.purchase_credits with the signature."
    ),
    annotations=READONLY_EXTERNAL,
)
async def get_tool_credits_requirements(
    credits: Desc[
        int | None,
        Field(
            description="Credit pack size to buy. Example: 100. Omit to use the server default pack."
        ),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity the credits will attach to."),
    ] = None,
) -> str:
    pack = credits or settings.tool_credit_pack_size

    return await _execute_tool(
        "commerce.credits_requirements",
        agent_id,
        lambda resolved: _sync_result(
            x402_services.build_tool_credits_requirements(resolved, pack)
        ),
    )


@mcp.tool(
    name="commerce.purchase_credits",
    title="Purchase tool credits",
    description=(
        "Verify an x402 payment and add per-use tool credits to the agent. "
        "Call after commerce.credits_requirements and a completed USDC payment."
    ),
    annotations=WRITE_PAYMENT,
)
async def purchase_tool_credits(
    payment_signature: Desc[
        str,
        Field(description="PAYMENT-SIGNATURE from the credits USDC payment."),
    ],
    payment_required: Desc[
        str,
        Field(description="PAYMENT-REQUIRED JSON returned by commerce.credits_requirements."),
    ],
    credits: Desc[
        int | None,
        Field(description="Credit pack size that was purchased. Must match the requirements call."),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(description="Agent identity to credit."),
    ] = None,
) -> str:
    pack = credits or settings.tool_credit_pack_size

    return await _execute_tool(
        "commerce.purchase_credits",
        agent_id,
        lambda resolved: x402_services.purchase_tool_credits(
            payment_signature, payment_required, resolved, pack
        ),
    )


@mcp.tool(
    name="commerce.stripe_checkout",
    title="Create Stripe checkout",
    description=(
        "Create a Stripe Checkout Session for Pro tier or tool credits (fiat rail). "
        "Use when the buyer pays by card instead of USDC; webhook fulfills the grant."
    ),
    annotations=WRITE_PAYMENT,
)
async def create_stripe_checkout(
    purpose: Desc[
        str,
        Field(
            description=(
                "Checkout purpose. Must be 'pro_tier_upgrade' or 'tool_credits'. "
                "Default pro_tier_upgrade."
            )
        ),
    ] = "pro_tier_upgrade",
    credits: Desc[
        int | None,
        Field(description="Required when purpose is tool_credits. Example: 100."),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(description="Agent identity the Stripe fulfillment will grant."),
    ] = None,
) -> str:
    if purpose not in ("pro_tier_upgrade", "tool_credits"):
        raise ValueError("purpose must be pro_tier_upgrade or tool_credits")

    return await _execute_tool(
        "commerce.stripe_checkout",
        agent_id,
        lambda resolved: _sync_result(
            stripe_payments.create_checkout_session(
                resolved,
                purpose,  # type: ignore[arg-type]
                credits=credits,
            )
        ),
    )


@mcp.tool(
    name="swarm.research",
    title="Run swarm research",
    description=(
        "Run the swarm agency: compose a research product from free inputs and list it for resale. "
        "Pass allow_paid_inputs=true only when buying upstream x402 services is intended."
    ),
    annotations=WRITE_PAYMENT,
)
async def run_swarm_research(
    topic: Desc[
        str,
        Field(description="Research topic to compose. Example: 'Base mainnet gas window'."),
    ],
    max_price_usdc: Desc[
        float | None,
        Field(description="Optional USDC ceiling for any paid upstream inputs."),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(description="Seller agent identity that will own the listing."),
    ] = None,
    allow_paid_inputs: Desc[
        bool | None,
        Field(
            description=(
                "If true, buy upstream x402 services before composing. Default false "
                "(free inputs only, unsold inventory costs nothing)."
            )
        ),
    ] = None,
) -> str:
    if not settings.swarm_enabled:
        return json.dumps(
            {
                "error": "SWARM_ENABLED is false; the buyer role is off on this "
                "deployment.",
                "data": None,
                "meta": None,
            },
            indent=2,
        )
    return await _execute_tool(
        "swarm.research",
        agent_id,
        lambda resolved: swarm_orchestrator.run_swarm_research(
            topic, resolved, max_price_usdc, allow_paid_inputs
        ),
    )


@mcp.tool(
    name="swarm.settle",
    title="Settle composite sale",
    description=(
        "Verify and settle a buyer's x402 payment for a listed composite product and record revenue. "
        "Call with product_id plus PAYMENT-SIGNATURE after the buyer pays."
    ),
    annotations=WRITE_PAYMENT,
)
async def settle_composite_sale(
    product_id: Desc[
        str,
        Field(description="Listed composite product id. Example: the hex id from swarm.research."),
    ],
    payment_signature: Desc[
        str,
        Field(description="PAYMENT-SIGNATURE from the buyer."),
    ],
    payment_required: Desc[
        str,
        Field(description="PAYMENT-REQUIRED terms for this product."),
    ],
    agent_id: Desc[
        str | None,
        Field(description="Seller agent identity recording the sale."),
    ] = None,
) -> str:
    return await _execute_tool(
        "swarm.settle",
        agent_id,
        lambda resolved: swarm_orchestrator.settle_composite_sale(
            product_id, payment_signature, payment_required, resolved
        ),
    )


@mcp.tool(
    name="swarm.revenue",
    title="Swarm revenue report",
    description=(
        "Get swarm portfolio revenue intelligence: spend, revenue, LTV:CAC, margins, per-source scores. "
        "Call after swarm.research or swarm.settle to inspect realized economics."
    ),
    annotations=READONLY,
)
async def swarm_revenue_report(
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    from app.swarm import sovereign

    return await _execute_tool(
        "swarm.revenue",
        agent_id,
        lambda _: _sync_result(sovereign.build_revenue_report()),
    )


@mcp.tool(
    name="pulse.base",
    title="Base network pulse",
    description=(
        "Get live Base Network Pulse: base fee, EIP-1559 projection, utilization, USD settlement cost, verdict. "
        "Call before settling on Base when you need a settle-now vs hold recommendation."
    ),
    annotations=READONLY_EXTERNAL,
)
async def get_base_pulse(
    depth: Desc[
        int | None,
        Field(description="Blocks to sample. Example: 12. Omit to use the server default."),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    from app import pulse

    return await _execute_tool(
        "pulse.base", agent_id, lambda _: pulse.get_pulse(depth)
    )


@mcp.tool(
    name="ops.metrics",
    title="Host OS metrics",
    description=(
        "Get host OS telemetry: CPU, memory, swap, disk, network, and an ok/warn/critical health verdict. "
        "Call to diagnose this MCP host; set include_processes=true for top memory processes."
    ),
    annotations=READONLY,
)
async def get_os_metrics(
    include_processes: Desc[
        bool,
        Field(description="If true, include top processes by memory. Default false."),
    ] = False,
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    from app import os_monitor

    return await _execute_tool(
        "ops.metrics",
        agent_id,
        lambda _: _sync_result(
            os_monitor.get_os_metrics(include_processes=include_processes)
        ),
    )


@mcp.tool(
    name="city.list",
    title="List US compliance cities",
    description=(
        "List US City Open-Data Compliance Network cities with paid_url, sample_url, and price. "
        "Call first, then city.sample, then city.check for the paid address lookup."
    ),
    annotations=READONLY,
)
async def list_us_cities(
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    from app.city_compliance import mcp_tools as city_mcp

    return await _execute_tool(
        "city.list", agent_id, lambda _: city_mcp.list_us_cities()
    )


@mcp.tool(
    name="city.sample",
    title="US city property sample",
    description=(
        "Get a free fixed-address property compliance sample for one US city code. "
        "Use before city.check to validate city_code and response shape without paying."
    ),
    annotations=READONLY_EXTERNAL,
)
async def get_us_city_property_sample(
    city_code: Desc[
        str,
        Field(
            description="City code from city.list. Examples: 'mn', 'sea', 'nyc', 'chi'."
        ),
    ],
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    from app.city_compliance import mcp_tools as city_mcp

    return await _execute_tool(
        "city.sample",
        agent_id,
        lambda _: city_mcp.get_us_city_property_sample(city_code),
    )


@mcp.tool(
    name="city.check",
    title="Paid US city property check",
    description=(
        "Run a paid US city property compliance check via x402 on the same HTTP resource buyers use. "
        "Prefer city.sample first. Settles USDC when EVM_PRIVATE_KEY is set; otherwise returns a 402 probe."
    ),
    annotations=WRITE_PAYMENT,
)
async def check_us_city_property(
    city_code: Desc[
        str,
        Field(description="City code from city.list. Example: 'mn'."),
    ],
    address: Desc[
        str,
        Field(
            description="Street address to check. Example: '1700 Penn Ave N' or '1 Centre St'."
        ),
    ],
    max_price_usdc: Desc[
        float | None,
        Field(description="Optional USDC spend ceiling. Example: 0.05."),
    ] = None,
    preferred_network: Desc[
        str | None,
        Field(description="Preferred CAIP-2 network. Example: 'eip155:8453'."),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    from app.city_compliance import mcp_tools as city_mcp

    return await _execute_tool(
        "city.check",
        agent_id,
        lambda _: city_mcp.check_us_city_property(
            city_code,
            address,
            max_price_usdc=max_price_usdc,
            preferred_network=preferred_network,
        ),
    )


@mcp.tool(
    name="mailrail.send",
    title="Send agent notification via MailRail",
    description=(
        "Dispatch transactional receipts, alert notifications, or agent communication over MailRail. "
        "Supports mock ledger, Resend API, SMTP, or Webhooks."
    ),
    annotations=WRITE_IDEMPOTENT,
)
async def mailrail_send(
    to: Desc[
        str,
        Field(description="Recipient email address, webhook identifier, or admin alias."),
    ],
    subject: Desc[
        str,
        Field(description="Notification subject line."),
    ],
    body: Desc[
        str,
        Field(description="Plain text or markdown content for the message."),
    ],
    event_id: Desc[
        str | None,
        Field(description="Optional deduplication key. Duplicate event IDs within a run window are silently dropped."),
    ] = None,
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    from app import mailrail

    return await _execute_tool(
        "mailrail.send",
        agent_id,
        lambda _: _sync_result(
            {
                "status": "ok",
                "mailrail": mailrail.send_agent_mail(
                    to=to,
                    subject=subject,
                    body=body,
                    event_id=event_id,
                ),
            }
        ),
    )


@mcp.tool(
    name="mailrail.status",
    title="Check MailRail health and configuration",
    description=(
        "Inspect MailRail provider status, active sender address, and dispatch capabilities."
    ),
    annotations=READONLY,
)
async def mailrail_status(
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    from app.config import settings

    return await _execute_tool(
        "mailrail.status",
        agent_id,
        lambda _: _sync_result(
            {
                "status": "ok",
                "enabled": settings.mailrail_enabled,
                "provider": settings.mailrail_provider,
                "from_address": settings.mailrail_from_address,
                "admin_recipient": settings.mailrail_admin_recipient,
                "has_api_key": bool(settings.mailrail_api_key),
                "has_webhook": bool(settings.mailrail_webhook_url),
                "has_smtp": bool(settings.mailrail_smtp_url),
            }
        ),
    )


@mcp.tool(
    name="mailrail.inbound",
    title="Ingest inbound agent message or webhook",
    description=(
        "Ingest an incoming message or webhook to the MailRail Postmaster agent with mention defusing and inbox ledger recording."
    ),
    annotations=WRITE_IDEMPOTENT,
)
async def mailrail_inbound(
    sender: Desc[
        str,
        Field(description="Sender address, agent ID, or system handle."),
    ],
    subject: Desc[
        str,
        Field(description="Subject line or topic."),
    ],
    body: Desc[
        str,
        Field(description="Message body text."),
    ],
    agent_id: Desc[
        str | None,
        Field(description="Optional agent identity for quota accounting."),
    ] = None,
) -> str:
    from app import mailrail

    return await _execute_tool(
        "mailrail.inbound",
        agent_id,
        lambda _: _sync_result(
            {
                "status": "ok",
                "inbound": mailrail.process_inbound_mail(
                    sender=sender,
                    subject=subject,
                    body=body,
                ),
            }
        ),
    )



@mcp.prompt(
    name="x402.buy_paid_api",
    title="Buy a paid x402 HTTP API",
    description="Walk an agent through discovering, probing, then paying for an x402 HTTP resource.",
)
def prompt_buy_paid_api(
    url: Desc[
        str | None,
        Field(description="Optional paid URL to probe. Omit to use the first x402.discover hit."),
    ] = None,
    query: Desc[
        str,
        Field(description="Bazaar search substring. Example: 'weather'."),
    ] = "weather",
) -> str:
    target = url or "the URL returned by x402.discover"
    return (
        f"Find a paid HTTP API matching {query!r} with x402.discover. "
        f"Then call x402.probe on {target} to read PAYMENT-REQUIRED "
        "(price, network, payTo) without spending. If the price is acceptable "
        "and this host has EVM_PRIVATE_KEY, call x402.pay_and_fetch with "
        "max_price_usdc set to your ceiling. If there is no spend key, return "
        "the 402 probe and how_to_pay instead of paying."
    )


@mcp.prompt(
    name="city.compliance_path",
    title="US city property compliance path",
    description="Golden path for US City Open-Data Compliance: list → sample → paid check.",
)
def prompt_city_compliance(
    city_code: Desc[
        str,
        Field(description="City code from city.list. Example: 'mn'."),
    ] = "mn",
    address: Desc[
        str,
        Field(description="Street address for city.check. Example: '1700 Penn Ave N'."),
    ] = "1700 Penn Ave N",
) -> str:
    return (
        "Call city.list to get supported city codes, paid_url, sample_url, and price. "
        f"Then city.sample with city_code={city_code!r} to validate the free envelope. "
        f"Then city.check with city_code={city_code!r} and address={address!r}. "
        "If EVM_PRIVATE_KEY is unset, city.check returns a 402 probe rather than charging."
    )


@mcp.resource(
    "x402://instructions",
    name="x402.instructions",
    title="x402 MCP routing instructions",
    description="Server routing guide: which dotted tool to call, in what order, for buyer/seller/city flows.",
    mime_type="text/plain",
)
def resource_instructions() -> str:
    return INSTRUCTIONS


@mcp.resource(
    "x402://catalog",
    name="x402.catalog",
    title="x402 MCP tool catalog",
    description="JSON catalog of dotted tool names, descriptions, and required env vars.",
    mime_type="application/json",
)
def resource_catalog() -> str:
    from app.tools_registry import TOOL_SPECS

    return json.dumps({"tools": list(TOOL_SPECS)}, indent=2)


@mcp.resource(
    "x402://agent-card",
    name="x402.agent-card",
    title="A2A Agent ID Card",
    description="Full A2A Protocol v1.0 Agent ID Card and capability descriptor.",
    mime_type="application/json",
)
def get_agent_card_resource() -> str:
    from app.agent_surface import agent_card

    return json.dumps(agent_card(), indent=2)


@mcp.resource(
    "x402://server-card",
    name="x402.server-card",
    title="MCP server card",
    description="Remote MCP Server Card for Smithery, Glama, and client indexing.",
    mime_type="application/json",
)
def get_server_card_resource() -> str:
    from app.agent_surface import mcp_server_card

    return json.dumps(mcp_server_card(), indent=2)


@mcp.resource(
    "x402://tools-manifest",
    name="x402.tools-manifest",
    title="MCP tools manifest",
    description="Canonical MCP well-known manifest with tool specs, quotas, and endpoints.",
    mime_type="application/json",
)
def get_tools_manifest_resource() -> str:
    from app.manifest import build_mcp_manifest

    return json.dumps(build_mcp_manifest(), indent=2)


@mcp.resource(
    "x402://pricing-table",
    name="x402.pricing-table",
    title="x402 pricing table",
    description="Machine-readable pricing for micropayments, subscriptions, and credits.",
    mime_type="application/json",
)
def get_pricing_table_resource() -> str:
    from app.agent_surface import paid_resources
    from app.payment_rails import build_payment_rails

    return json.dumps(
        {
            "free_tier": {
                "monthly_quota": settings.free_tier_monthly_quota,
                "rate_limit_per_minute": settings.free_tier_rate_limit_per_min,
                "price": "$0.00",
            },
            "pro_tier": {
                "monthly_quota": settings.pro_tier_monthly_quota,
                "rate_limit_per_minute": settings.pro_tier_rate_limit_per_min,
                "price_usd": "$29.00",
                "price_x402": settings.pro_tier_price,
            },
            "tool_credits": {
                "pack_size": settings.tool_credit_pack_size,
                "price_x402": settings.tool_credit_pack_price,
            },
            "paid_endpoints": paid_resources(),
            "payment_rails": build_payment_rails(),
        },
        indent=2,
    )


async def _sync_result(data: dict[str, Any]) -> dict[str, Any]:
    return data


def _simplify_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    new_schema = schema.copy()
    if "anyOf" in schema:
        subtypes = [t for t in schema["anyOf"] if isinstance(t, dict) and t.get("type") != "null"]
        if len(subtypes) == 1:
            sub = subtypes[0]
            for k in list(new_schema.keys()):
                if k not in ("default", "title", "description"):
                    new_schema.pop(k, None)
            new_schema.update(_simplify_schema(sub))
            new_schema.pop("anyOf", None)
        else:
            new_schema["anyOf"] = [_simplify_schema(t) for t in schema["anyOf"]]
    if "properties" in new_schema:
        new_schema["properties"] = {
            k: _simplify_schema(v) for k, v in new_schema["properties"].items()
        }
    if "items" in new_schema:
        new_schema["items"] = _simplify_schema(new_schema["items"])
    return new_schema


# Simplify the parameter schemas of all registered tools to prevent validation errors (status 422) on strict client parsers.
for tool in mcp._tool_manager._tools.values():
    tool.parameters = _simplify_schema(tool.parameters)
