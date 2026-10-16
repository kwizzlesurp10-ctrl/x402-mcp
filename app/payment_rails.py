"""Payment rail catalog — Stripe primary, x402/Coinbase alternate."""

from __future__ import annotations

from app.config import settings

# Solana mainnet CAIP-2 (SVM). Seller-only boxes never hold SVM_PRIVATE_KEY.
SOLANA_MAINNET = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"


def build_payment_rails() -> dict:
    """Document available payment rails for manifest and /upgrade."""
    from app import x402_services

    svm_registered = x402_services.svm_available()
    return {
        "stripe": {
            "primary": True,
            "description": "Fiat checkout rail for Pro tier and tool credit packs",
            "configured": bool(getattr(settings, "stripe_secret_key", None)),
            "checkout_endpoints": ["/stripe/checkout", "/stripe/webhook"],
        },
        "x402_coinbase": {
            "primary": True,
            "description": (
                "Crypto micropayments via x402 protocol and Coinbase CDP"
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
        "x402_svm": {
            "primary": False,
            "description": (
                "Solana (SVM) exact scheme for seller listings. Public host "
                "registers solana:* when x402[svm] is installed; no spend key "
                "on this box."
            ),
            "network": SOLANA_MAINNET,
            "pattern": "solana:*",
            "scheme": "exact",
            "requires_env": ["X402_PAY_TO_ADDRESS"],
            "configured": bool(settings.x402_pay_to_address),
            "registered": svm_registered,
            "settle": (
                "live-scheme-registered"
                if svm_registered
                else "unavailable-x402-svm-extra-missing"
            ),
            "facilitator_note": (
                "CDP/x402 facilitator settle on Solana mainnet is not claimed "
                "until the facilitator advertises SVM support. Listings may "
                "include solana:* accepts; settlement can fail until then."
            ),
        },
        "mailrail": {
            "primary": False,
            "description": "Transactional agent communication, alert dispatch, and receipt messaging rail",
            "provider": settings.mailrail_provider,
            "configured": bool(settings.mailrail_enabled or settings.mailrail_provider == "mock"),
        },
    }