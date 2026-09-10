"""Payment rail catalog — Stripe primary, x402/Coinbase alternate."""

from __future__ import annotations

from app.config import settings


def build_payment_rails() -> dict:
    """Document available payment rails for manifest and /upgrade."""
    return {
        "stripe": {
            "primary": True,
            "description": "Fiat card/bank payments via Stripe Checkout",
            "initiation": {
                "http": "POST /stripe/checkout",
                "mcp_tool": "commerce.stripe_checkout",
            },
            "webhook": "/stripe/webhook",
            "requires_env": ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"],
            "configured": bool(settings.stripe_secret_key),
        },
        "x402_coinbase": {
            "primary": False,
            "description": (
                "Crypto micropayments via x402 protocol and Coinbase CDP "
                "(future/alternate rail)"
            ),
            "initiation": {
                "pro_upgrade": [
                    "commerce.pro_requirements",
                    "commerce.activate_pro",
                ],
                "tool_credits": [
                    "commerce.credits_requirements",
                    "commerce.purchase_credits",
                ],
            },
            "facilitator_url": settings.x402_facilitator_url,
            "discovery_url": settings.cdp_discovery_url,
            "requires_env": ["X402_PAY_TO_ADDRESS"],
            "configured": bool(settings.x402_pay_to_address),
        },
        "mailrail": {
            "primary": False,
            "description": "Transactional agent communication, alert dispatch, and receipt messaging rail",
            "provider": settings.mailrail_provider,
            "configured": bool(settings.mailrail_enabled or settings.mailrail_provider == "mock"),
        },
    }