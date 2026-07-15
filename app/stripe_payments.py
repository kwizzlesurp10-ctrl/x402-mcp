"""Stripe payment rail — Checkout initiation, webhook verify, commerce fulfillment."""

from __future__ import annotations

import json
from typing import Any, Literal

from app.commerce import quota_store
from app.config import settings

PurchasePurpose = Literal["pro_tier_upgrade", "tool_credits"]


class StripeNotConfiguredError(ValueError):
    """Raised when STRIPE_SECRET_KEY is absent."""


class StripeWebhookError(ValueError):
    """Raised on invalid or unverifiable webhook payloads."""


def _require_secret_key() -> str:
    if not settings.stripe_secret_key:
        raise StripeNotConfiguredError(
            "STRIPE_SECRET_KEY required for Stripe payments. "
            "Set it in .env or use x402/Coinbase alternate rails."
        )
    return settings.stripe_secret_key


def price_usd_to_cents(price: str) -> int:
    """Convert '$29.00' style price strings to Stripe cents."""
    cleaned = price.replace("$", "").strip()
    return int(round(float(cleaned) * 100))


def _configure_stripe() -> None:
    import stripe

    stripe.api_key = _require_secret_key()


def create_checkout_session(
    agent_id: str,
    purpose: PurchasePurpose,
    *,
    credits: int | None = None,
) -> dict[str, Any]:
    """Create a Stripe Checkout Session for pro tier or tool credits."""
    import stripe

    _configure_stripe()

    if purpose == "pro_tier_upgrade":
        amount_cents = price_usd_to_cents(settings.pro_tier_price)
        product_name = "x402 MCP Pro Tier"
        pack_credits = None
    elif purpose == "tool_credits":
        pack_credits = credits or settings.tool_credit_pack_size
        amount_cents = price_usd_to_cents(settings.tool_credit_pack_price)
        product_name = f"x402 MCP Tool Credits ({pack_credits})"
    else:
        raise ValueError(f"Unknown purchase purpose: {purpose}")

    metadata: dict[str, str] = {
        "agent_id": agent_id,
        "purpose": purpose,
    }
    if pack_credits is not None:
        metadata["credits"] = str(pack_credits)

    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=f"{settings.public_base_url}/upgrade?stripe=success",
        cancel_url=f"{settings.public_base_url}/upgrade?stripe=cancel",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": amount_cents,
                    "product_data": {"name": product_name},
                },
                "quantity": 1,
            }
        ],
        metadata=metadata,
        payment_intent_data={"metadata": metadata},
    )

    return {
        "rail": "stripe",
        "checkout_url": session.url,
        "session_id": session.id,
        "agent_id": agent_id,
        "purpose": purpose,
        "credits": pack_credits,
        "amount_cents": amount_cents,
        "currency": "usd",
    }


def verify_webhook_payload(payload: bytes, signature_header: str | None) -> dict[str, Any]:
    """Verify Stripe-Signature and return the parsed event dict."""
    import stripe

    if not settings.stripe_webhook_secret:
        raise StripeWebhookError("STRIPE_WEBHOOK_SECRET not configured")
    if not signature_header:
        raise StripeWebhookError("Missing Stripe-Signature header")

    try:
        stripe.Webhook.construct_event(
            payload,
            signature_header,
            settings.stripe_webhook_secret,
        )
    except stripe.error.SignatureVerificationError as exc:
        raise StripeWebhookError(f"Invalid Stripe signature: {exc}") from exc

    return json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)


def _metadata_from_event(event: dict[str, Any]) -> dict[str, str]:
    obj = event.get("data", {}).get("object", {})
    metadata = obj.get("metadata") or {}
    if metadata:
        return {k: str(v) for k, v in metadata.items()}

    if event.get("type") == "checkout.session.completed":
        payment_intent_id = obj.get("payment_intent")
        if payment_intent_id:
            import stripe

            _configure_stripe()
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            return {k: str(v) for k, v in (intent.metadata or {}).items()}

    return {}


def fulfillment_key_from_event(event: dict[str, Any]) -> str | None:
    """Stable purchase idempotency key shared across checkout + payment_intent events."""
    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if event_type == "payment_intent.succeeded":
        pi_id = obj.get("id")
        return f"pi:{pi_id}" if pi_id else None

    if event_type == "checkout.session.completed":
        pi_id = obj.get("payment_intent")
        if pi_id:
            return f"pi:{pi_id}"
        cs_id = obj.get("id")
        return f"cs:{cs_id}" if cs_id else None

    return None


def fulfill_stripe_event(event: dict[str, Any]) -> dict[str, Any]:
    """Map verified Stripe events to commerce fulfillment (idempotent per purchase)."""
    event_id = event.get("id", "")
    event_type = event.get("type", "")

    if event_type not in ("checkout.session.completed", "payment_intent.succeeded"):
        return {"handled": False, "event_type": event_type, "event_id": event_id}

    fulfillment_key = fulfillment_key_from_event(event)
    if not fulfillment_key:
        return {
            "handled": False,
            "event_type": event_type,
            "event_id": event_id,
            "reason": "missing payment_intent or session id for idempotency",
        }

    metadata = _metadata_from_event(event)
    agent_id = metadata.get("agent_id")
    purpose = metadata.get("purpose")

    if not agent_id or not purpose:
        return {
            "handled": False,
            "event_type": event_type,
            "event_id": event_id,
            "fulfillment_key": fulfillment_key,
            "reason": "missing agent_id or purpose metadata",
        }

    if purpose == "pro_tier_upgrade":
        result = quota_store.fulfill_stripe_pro_tier(agent_id, fulfillment_key)
    elif purpose == "tool_credits":
        credits = int(metadata.get("credits", settings.tool_credit_pack_size))
        result = quota_store.fulfill_stripe_credits(agent_id, credits, fulfillment_key)
    else:
        return {
            "handled": False,
            "event_type": event_type,
            "event_id": event_id,
            "fulfillment_key": fulfillment_key,
            "reason": f"unknown purpose: {purpose}",
        }

    return {
        "handled": True,
        "event_type": event_type,
        "event_id": event_id,
        "fulfillment_key": fulfillment_key,
        "fulfillment": result,
    }


def handle_stripe_webhook(payload: bytes, signature_header: str | None) -> dict[str, Any]:
    """Verify webhook signature and dispatch fulfillment."""
    event = verify_webhook_payload(payload, signature_header)
    return fulfill_stripe_event(event)


def build_test_webhook_signature(payload: bytes, secret: str) -> str:
    """Generate a valid Stripe-Signature for test fixtures (matches stripe._webhook)."""
    import hashlib
    import hmac
    import time

    payload_str = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    timestamp = int(time.time())
    signed = f"{timestamp}.{payload_str}"
    digest = hmac.new(
        secret.encode("utf-8"),
        signed.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"