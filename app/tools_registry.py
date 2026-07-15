"""Canonical MCP tool inventory — single source for manifest, tests, and verification."""

from __future__ import annotations

from typing import TypedDict


class ToolSpec(TypedDict, total=False):
    name: str
    description: str
    tier: str
    requires_env: list[str]


TOOL_SPECS: tuple[ToolSpec, ...] = (
    {
        "name": "discover_services",
        "description": "Discover x402 Bazaar paid HTTP services",
        "tier": "free",
    },
    {
        "name": "get_payment_requirements",
        "description": "Probe URL for HTTP 402 payment requirements",
        "tier": "free",
    },
    {
        "name": "pay_and_fetch",
        "description": "Pay via x402 and fetch protected resource",
        "tier": "free",
        "requires_env": ["EVM_PRIVATE_KEY"],
    },
    {
        "name": "build_seller_requirements",
        "description": "Build seller payment requirements",
        "tier": "free",
        "requires_env": ["X402_PAY_TO_ADDRESS"],
    },
    {
        "name": "verify_payment_payload",
        "description": "Verify payment signature via facilitator",
        "tier": "free",
    },
    {
        "name": "get_supported_networks",
        "description": "List networks, facilitators, and headers",
        "tier": "free",
    },
    {
        "name": "get_pro_upgrade_requirements",
        "description": "Build x402 payment requirements for Pro tier upgrade",
        "tier": "free",
        "requires_env": ["X402_PAY_TO_ADDRESS"],
    },
    {
        "name": "activate_pro_tier",
        "description": "Verify x402 payment and unlock Pro tier quota",
        "tier": "free",
    },
    {
        "name": "get_tool_credits_requirements",
        "description": "Build x402 payment requirements for per-use tool credits",
        "tier": "free",
        "requires_env": ["X402_PAY_TO_ADDRESS"],
    },
    {
        "name": "purchase_tool_credits",
        "description": "Verify x402 payment and add per-use tool credits",
        "tier": "free",
    },
    {
        "name": "create_stripe_checkout",
        "description": "Create Stripe Checkout Session for pro tier or tool credits",
        "tier": "free",
        "requires_env": ["STRIPE_SECRET_KEY"],
    },
    {
        "name": "run_swarm_research",
        "description": "Run the swarm Agency: buy cheap upstream x402 services, "
        "compose a composite research report, and list it for resale",
        "tier": "free",
        "requires_env": ["EVM_PRIVATE_KEY", "X402_PAY_TO_ADDRESS"],
    },
    {
        "name": "settle_composite_sale",
        "description": "Verify + settle a buyer's x402 payment for a listed "
        "composite product and record the revenue",
        "tier": "free",
    },
    {
        "name": "swarm_revenue_report",
        "description": "Portfolio revenue intelligence: spend, revenue, LTV:CAC, "
        "margins, per-source profit scores",
        "tier": "free",
    },
)

EXPECTED_TOOL_NAMES: frozenset[str] = frozenset(spec["name"] for spec in TOOL_SPECS)
TOOL_COUNT = len(TOOL_SPECS)