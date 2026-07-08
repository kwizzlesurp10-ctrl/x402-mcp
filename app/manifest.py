"""MCP well-known manifest for Grok/Cursor connector discovery."""

from app.config import settings


def build_mcp_manifest() -> dict:
    return {
        "name": "x402-micropayments",
        "version": "0.1.0",
        "description": (
            "Production MCP server for x402 HTTP micropayments — discover paid "
            "services, probe 402 requirements, pay-and-fetch resources, and "
            "build/verify seller payment configs."
        ),
        "protocol": "mcp",
        "transport": ["stdio", "streamable-http", "sse"],
        "capabilities": {
            "tools": True,
            "resources": False,
            "prompts": False,
        },
        "tools": [
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
        ],
        "tiers": {
            "free": {
                "monthly_quota": settings.free_tier_monthly_quota,
                "rate_limit_per_minute": settings.free_tier_rate_limit_per_min,
                "quota_warning_threshold": 0.8,
                "price_usd": 0,
            },
            "pro": {
                "monthly_quota": settings.pro_tier_monthly_quota,
                "rate_limit_per_minute": settings.pro_tier_rate_limit_per_min,
                "price_usd": 29,
                "price_x402": settings.pro_tier_price,
                "upgrade_url": settings.upgrade_url,
                "payment_tools": ["get_pro_upgrade_requirements", "activate_pro_tier"],
            },
        },
        "upgrade_url": settings.upgrade_url,
        "x402": {
            "protocol_version": "v2",
            "default_network": settings.x402_default_network,
            "facilitator_url": settings.x402_facilitator_url,
            "headers": {
                "payment_required": "PAYMENT-REQUIRED",
                "payment_signature": "PAYMENT-SIGNATURE",
                "payment_response": "PAYMENT-RESPONSE",
            },
        },
        "endpoints": {
            "manifest": "/.well-known/mcp",
            "health": "/health",
            "upgrade": "/upgrade",
            "mcp_sse": "/mcp/sse",
        },
        "connector_url": f"{settings.public_base_url}/mcp/sse",
    }