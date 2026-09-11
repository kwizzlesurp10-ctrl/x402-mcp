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
        "name": "x402.agent_card",
        "description": (
            "Return the A2A Protocol v1.0 Agent ID Card and MCP server card. "
            "Optional target_id filters to a skill id, name, or tag."
        ),
        "tier": "free",
    },
    {
        "name": "x402.discover",
        "description": (
            "Discover paid HTTP APIs in the x402 Bazaar via the facilitator catalog. "
            "Call this first to find a resource URL, then x402.probe and x402.pay_and_fetch."
        ),
        "tier": "free",
    },
    {
        "name": "x402.probe",
        "description": (
            "Probe a URL for HTTP 402 PAYMENT-REQUIRED terms using the x402 client SDK. "
            "Use before x402.pay_and_fetch to inspect price, network, and payTo without spending."
        ),
        "tier": "free",
    },
    {
        "name": "x402.pay_and_fetch",
        "description": (
            "Pay USDC via x402 and fetch a protected HTTP resource in one call. "
            "Requires EVM_PRIVATE_KEY on this host; otherwise use x402.probe for a no-spend 402."
        ),
        "tier": "free",
        "requires_env": ["EVM_PRIVATE_KEY"],
    },
    {
        "name": "x402.build_seller",
        "description": (
            "Build seller-side x402 payment requirements for your own HTTP resource. "
            "Pass resource_url plus discovery_* fields to catalog the endpoint in Bazaar."
        ),
        "tier": "free",
        "requires_env": ["X402_PAY_TO_ADDRESS"],
    },
    {
        "name": "x402.verify",
        "description": (
            "Verify an x402 PAYMENT-SIGNATURE against PAYMENT-REQUIRED terms via the facilitator. "
            "Call after a buyer presents a signature and before releasing paid content."
        ),
        "tier": "free",
    },
    {
        "name": "x402.networks",
        "description": (
            "List supported settlement networks, facilitators, and x402 v2 header names. "
            "Call when choosing a preferred_network for x402.pay_and_fetch or x402.build_seller."
        ),
        "tier": "free",
    },
    {
        "name": "commerce.pro_requirements",
        "description": (
            "Build x402 payment requirements to purchase the Pro quota tier. "
            "Next: pay those terms, then commerce.activate_pro with the signature."
        ),
        "tier": "free",
        "requires_env": ["X402_PAY_TO_ADDRESS"],
    },
    {
        "name": "commerce.activate_pro",
        "description": (
            "Verify a Pro-tier x402 payment and unlock Pro quota limits for the agent. "
            "Call after commerce.pro_requirements and a completed USDC payment."
        ),
        "tier": "free",
    },
    {
        "name": "commerce.credits_requirements",
        "description": (
            "Build x402 payment requirements to buy a pack of per-use MCP tool credits. "
            "Next: pay those terms, then commerce.purchase_credits with the signature."
        ),
        "tier": "free",
        "requires_env": ["X402_PAY_TO_ADDRESS"],
    },
    {
        "name": "commerce.purchase_credits",
        "description": (
            "Verify an x402 payment and add per-use tool credits to the agent. "
            "Call after commerce.credits_requirements and a completed USDC payment."
        ),
        "tier": "free",
    },
    {
        "name": "commerce.stripe_checkout",
        "description": (
            "Create a Stripe Checkout Session for Pro tier or tool credits (fiat rail). "
            "Use when the buyer pays by card instead of USDC; webhook fulfills the grant."
        ),
        "tier": "free",
        "requires_env": ["STRIPE_SECRET_KEY"],
    },
    {
        "name": "swarm.research",
        "description": (
            "Run the swarm agency: compose a research product from free inputs and list it for resale. "
            "Pass allow_paid_inputs=true only when buying upstream x402 services is intended."
        ),
        "tier": "free",
        "requires_env": ["EVM_PRIVATE_KEY", "X402_PAY_TO_ADDRESS"],
    },
    {
        "name": "swarm.settle",
        "description": (
            "Verify and settle a buyer's x402 payment for a listed composite product and record revenue. "
            "Call with product_id plus PAYMENT-SIGNATURE after the buyer pays."
        ),
        "tier": "free",
    },
    {
        "name": "swarm.revenue",
        "description": (
            "Get swarm portfolio revenue intelligence: spend, revenue, LTV:CAC, margins, per-source scores. "
            "Call after swarm.research or swarm.settle to inspect realized economics."
        ),
        "tier": "free",
    },
    {
        "name": "pulse.base",
        "description": (
            "Get live Base Network Pulse: base fee, EIP-1559 projection, utilization, USD settlement cost, verdict. "
            "Call before settling on Base when you need a settle-now vs hold recommendation."
        ),
        "tier": "free",
    },
    {
        "name": "ops.metrics",
        "description": (
            "Get host OS telemetry: CPU, memory, swap, disk, network, and an ok/warn/critical health verdict. "
            "Call to diagnose this MCP host; set include_processes=true for top memory processes."
        ),
        "tier": "free",
    },
    {
        "name": "city.list",
        "description": (
            "List US City Open-Data Compliance Network cities with paid_url, sample_url, and price. "
            "Call first, then city.sample, then city.check for the paid address lookup."
        ),
        "tier": "free",
    },
    {
        "name": "city.sample",
        "description": (
            "Get a free fixed-address property compliance sample for one US city code. "
            "Use before city.check to validate city_code and response shape without paying."
        ),
        "tier": "free",
    },
    {
        "name": "city.check",
        "description": (
            "Run a paid US city property compliance check via x402 on the same HTTP resource buyers use. "
            "Prefer city.sample first. Settles USDC when EVM_PRIVATE_KEY is set; otherwise returns a 402 probe."
        ),
        "tier": "free",
        "requires_env": ["EVM_PRIVATE_KEY"],
    },
    {
        "name": "mailrail.send",
        "description": (
            "Dispatch transactional receipts, alert notifications, or agent communication over MailRail. "
            "Supports mock ledger, Resend API, SMTP, or Webhooks."
        ),
        "tier": "free",
    },
    {
        "name": "mailrail.status",
        "description": (
            "Inspect MailRail provider status, active sender address, and dispatch capabilities. "
            "Call to verify communication rail readiness before dispatching receipts or alerts."
        ),
        "tier": "free",
    },
    {
        "name": "mailrail.inbound",
        "description": (
            "Ingest or route an inbound message to the MailRail Postmaster agent with mention defusing and inbox ledger recording."
        ),
        "tier": "free",
    },
)

EXPECTED_TOOL_NAMES: frozenset[str] = frozenset(spec["name"] for spec in TOOL_SPECS)
TOOL_COUNT = len(TOOL_SPECS)

