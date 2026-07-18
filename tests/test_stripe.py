"""Stripe payment rail tests — init, webhook verify, fulfillment, x402 preserved."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.commerce import InMemoryQuotaStore
from app.config import settings
from app.main import app
from app import stripe_payments

WEBHOOK_SECRET = "whsec_test_secret_for_unit_tests"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def store() -> InMemoryQuotaStore:
    return InMemoryQuotaStore()


def _checkout_event(
    event_id: str,
    *,
    agent_id: str,
    purpose: str,
    credits: str | None = None,
    event_type: str = "checkout.session.completed",
    payment_intent_id: str = "pi_test_shared_001",
    session_id: str = "cs_test_session_001",
) -> bytes:
    metadata = {"agent_id": agent_id, "purpose": purpose}
    if credits is not None:
        metadata["credits"] = credits

    if event_type == "payment_intent.succeeded":
        obj: dict = {"id": payment_intent_id, "metadata": metadata}
    else:
        obj = {
            "id": session_id,
            "payment_intent": payment_intent_id,
            "metadata": metadata,
        }

    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "type": event_type,
            "data": {"object": obj},
        }
    ).encode()


def test_create_checkout_session_pro_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fixture")
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8402")

    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/c/pay/cs_test_pro"
    mock_session.id = "cs_test_pro"

    with patch("stripe.checkout.Session.create", return_value=mock_session) as create:
        result = stripe_payments.create_checkout_session(
            "agent-stripe-1", "pro_tier_upgrade"
        )

    assert result["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_pro"
    assert result["session_id"] == "cs_test_pro"
    assert result["agent_id"] == "agent-stripe-1"
    assert result["purpose"] == "pro_tier_upgrade"
    assert result["rail"] == "stripe"
    create.assert_called_once()
    call_kwargs = create.call_args.kwargs
    assert call_kwargs["metadata"]["agent_id"] == "agent-stripe-1"
    assert call_kwargs["metadata"]["purpose"] == "pro_tier_upgrade"


def test_create_checkout_session_tool_credits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fixture")

    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/c/pay/cs_test_credits"
    mock_session.id = "cs_test_credits"

    with patch("stripe.checkout.Session.create", return_value=mock_session):
        result = stripe_payments.create_checkout_session(
            "agent-credits", "tool_credits", credits=50
        )

    assert result["purpose"] == "tool_credits"
    assert result["credits"] == 50


def test_create_checkout_requires_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", None)
    with pytest.raises(stripe_payments.StripeNotConfiguredError):
        stripe_payments.create_checkout_session("a", "pro_tier_upgrade")


def test_webhook_valid_signature_unlocks_pro(
    monkeypatch: pytest.MonkeyPatch, store: InMemoryQuotaStore
) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(stripe_payments, "quota_store", store)

    payload = _checkout_event(
        "evt_pro_unlock", agent_id="webhook-agent", purpose="pro_tier_upgrade"
    )
    sig = stripe_payments.build_test_webhook_signature(payload, WEBHOOK_SECRET)

    result = stripe_payments.handle_stripe_webhook(payload, sig)

    assert result["handled"] is True
    assert store.get_tier("webhook-agent") == "pro"


def test_webhook_valid_signature_adds_credits(
    monkeypatch: pytest.MonkeyPatch, store: InMemoryQuotaStore
) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(stripe_payments, "quota_store", store)

    payload = _checkout_event(
        "evt_credits_add",
        agent_id="credits-agent",
        purpose="tool_credits",
        credits="25",
        event_type="payment_intent.succeeded",
    )
    sig = stripe_payments.build_test_webhook_signature(payload, WEBHOOK_SECRET)

    result = stripe_payments.handle_stripe_webhook(payload, sig)

    assert result["handled"] is True
    assert store.get_credits("credits-agent") == 25


def test_webhook_invalid_signature_rejects(
    monkeypatch: pytest.MonkeyPatch, store: InMemoryQuotaStore
) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(stripe_payments, "quota_store", store)

    payload = _checkout_event(
        "evt_bad_sig", agent_id="no-change", purpose="pro_tier_upgrade"
    )

    with pytest.raises(stripe_payments.StripeWebhookError):
        stripe_payments.handle_stripe_webhook(payload, "t=0,v1=invalid")

    assert store.get_tier("no-change") == "free"


def test_webhook_idempotent_no_double_fulfill(
    monkeypatch: pytest.MonkeyPatch, store: InMemoryQuotaStore
) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(stripe_payments, "quota_store", store)

    payload = _checkout_event(
        "evt_idem", agent_id="idem-agent", purpose="tool_credits", credits="10"
    )
    sig = stripe_payments.build_test_webhook_signature(payload, WEBHOOK_SECRET)

    stripe_payments.handle_stripe_webhook(payload, sig)
    stripe_payments.handle_stripe_webhook(payload, sig)

    assert store.get_credits("idem-agent") == 10


def test_dual_event_same_purchase_fulfills_once(
    monkeypatch: pytest.MonkeyPatch, store: InMemoryQuotaStore
) -> None:
    """checkout.session.completed + payment_intent.succeeded must not double-credit."""
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(stripe_payments, "quota_store", store)

    pi_id = "pi_dual_purchase_001"
    checkout_payload = _checkout_event(
        "evt_checkout_dual",
        agent_id="dual-agent",
        purpose="tool_credits",
        credits="100",
        payment_intent_id=pi_id,
    )
    intent_payload = _checkout_event(
        "evt_intent_dual",
        agent_id="dual-agent",
        purpose="tool_credits",
        credits="100",
        event_type="payment_intent.succeeded",
        payment_intent_id=pi_id,
    )

    for payload in (checkout_payload, intent_payload):
        sig = stripe_payments.build_test_webhook_signature(payload, WEBHOOK_SECRET)
        result = stripe_payments.handle_stripe_webhook(payload, sig)
        assert result["handled"] is True

    assert store.get_credits("dual-agent") == 100


def test_missing_fulfillment_key_does_not_block_other_agents(
    monkeypatch: pytest.MonkeyPatch, store: InMemoryQuotaStore
) -> None:
    """Events without payment/session ids must not poison idempotency for other agents."""
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(stripe_payments, "quota_store", store)

    bad_payload = json.dumps(
        {
            "id": "",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {
                        "agent_id": "agent-a",
                        "purpose": "pro_tier_upgrade",
                    }
                }
            },
        }
    ).encode()
    good_payload = _checkout_event(
        "evt_agent_b",
        agent_id="agent-b",
        purpose="pro_tier_upgrade",
        payment_intent_id="pi_agent_b_only",
    )

    bad_sig = stripe_payments.build_test_webhook_signature(bad_payload, WEBHOOK_SECRET)
    bad_result = stripe_payments.handle_stripe_webhook(bad_payload, bad_sig)
    assert bad_result["handled"] is False
    assert store.get_tier("agent-a") == "free"

    good_sig = stripe_payments.build_test_webhook_signature(good_payload, WEBHOOK_SECRET)
    good_result = stripe_payments.handle_stripe_webhook(good_payload, good_sig)
    assert good_result["handled"] is True
    assert store.get_tier("agent-b") == "pro"


def test_http_stripe_checkout_route(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fixture")

    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/c/pay/cs_http"
    mock_session.id = "cs_http"

    with patch("stripe.checkout.Session.create", return_value=mock_session):
        response = client.post(
            "/stripe/checkout",
            json={"agent_id": "http-agent", "purpose": "pro_tier_upgrade"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_http"
    assert body["agent_id"] == "http-agent"
    assert body["purpose"] == "pro_tier_upgrade"


def test_http_stripe_checkout_unconfigured(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", None)
    response = client.post(
        "/stripe/checkout",
        json={"purpose": "pro_tier_upgrade"},
    )
    assert response.status_code == 503
    assert "STRIPE_SECRET_KEY" in response.json()["detail"]


def test_http_webhook_valid_returns_200(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, store: InMemoryQuotaStore
) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr("app.main.quota_store", store)
    monkeypatch.setattr(stripe_payments, "quota_store", store)

    payload = _checkout_event(
        "evt_http_ok", agent_id="http-wh-agent", purpose="pro_tier_upgrade"
    )
    sig = stripe_payments.build_test_webhook_signature(payload, WEBHOOK_SECRET)

    response = client.post(
        "/stripe/webhook",
        content=payload,
        headers={"Stripe-Signature": sig},
    )

    assert response.status_code == 200
    assert response.json()["handled"] is True
    assert store.get_tier("http-wh-agent") == "pro"


def test_http_webhook_invalid_returns_400(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, store: InMemoryQuotaStore
) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr("app.main.quota_store", store)

    payload = _checkout_event(
        "evt_http_bad", agent_id="unchanged", purpose="pro_tier_upgrade"
    )

    response = client.post(
        "/stripe/webhook",
        content=payload,
        headers={"Stripe-Signature": "bad"},
    )

    assert response.status_code == 400
    assert store.get_tier("unchanged") == "free"


def test_upgrade_lists_stripe_and_x402(client: TestClient) -> None:
    response = client.get("/upgrade")
    assert response.status_code == 200
    body = response.json()
    assert "stripe" in body
    assert body["stripe"]["checkout_endpoint"] == "/stripe/checkout"
    assert "x402_coinbase" in body
    assert body["x402_coinbase"]["status"] == "alternate_future_rail"
    assert "get_pro_upgrade_requirements" in body["mcp_tools"]["pro_upgrade_x402"]


def test_manifest_payment_rails(client: TestClient) -> None:
    manifest = client.get("/.well-known/mcp").json()
    rails = manifest["payment_rails"]
    assert rails["stripe"]["primary"] is True
    assert rails["x402_coinbase"]["primary"] is False
    assert "create_stripe_checkout" in rails["stripe"]["initiation"]["mcp_tool"]
    tool_names = {t["name"] for t in manifest["tools"]}
    assert "create_stripe_checkout" in tool_names
    assert "get_pro_upgrade_requirements" in tool_names