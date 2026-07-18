"""MCP well-known manifest for Grok/Cursor connector discovery."""

from app.config import settings
from app.payment_rails import build_payment_rails
from app.tools_registry import TOOL_SPECS


def build_mcp_manifest() -> dict:
    tools = [
        {
            "name": spec["name"],
            "description": spec["description"],
            "tier": spec.get("tier", "free"),
            **({"requires_env": spec["requires_env"]} if spec.get("requires_env") else {}),
        }
        for spec in TOOL_SPECS
    ]
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
        "tools": tools,
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
        "payment_rails": build_payment_rails(),
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
            "stats": "/stats",
            "doctor": "/doctor",
            "probe": "/probe",
            "wallet": "/wallet",
            "events": "/events",
            "ledger_spend": "/ledger/spend",
            "ledger_revenue": "/ledger/revenue",
            "seller_requirements": "/seller/requirements",
            "stripe_checkout": "/stripe/checkout",
            "stripe_webhook": "/stripe/webhook",
            "mcp_sse": "/mcp/sse",
        },
        "connector_url": f"{settings.public_base_url}/mcp/sse",
    }