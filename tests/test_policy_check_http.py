"""HTTP POST /x402/policy-check — 402 unpaid, paid path with mocked settle."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from x402.http import encode_payment_required_header
from x402.schemas import PaymentRequired, PaymentRequirements

from app import policy_check
from app.config import settings
from app.main import app

client = TestClient(app)


def _merchant_header() -> str:
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x1111111111111111111111111111111111111111",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="5000",
        max_timeout_seconds=300,
        extra={},
    )
    return encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="merchant")
    )


@pytest.fixture
def policy_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "policy_check_enabled", True)
    assert settings.x402_pay_to_address


def test_unpaid_returns_402_with_payment_required(policy_on: None) -> None:
    resp = client.post("/x402/policy-check", json={"payment_required_header": _merchant_header(), "policy": {}})
    assert resp.status_code == 402
    assert "PAYMENT-REQUIRED" in resp.headers
    body = resp.json()
    assert body.get("error") == "payment_required"
    assert body.get("product_id") == policy_check.PRODUCT_ID


def test_feature_disabled_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "policy_check_enabled", False)
    r = client.post("/x402/policy-check", json={})
    assert r.status_code == 503
    assert r.json().get("error") == "feature_disabled"


def test_paid_success_and_idempotency(
    policy_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # In CI, REDIS_URL may be set while the client is unreachable — strict idempotency
    # would 503. Policy-check idempotency falls back to in-memory when Redis is unset.
    monkeypatch.setattr(settings, "redis_url", None)

    async def fake_settle(_sig: str, _hdr: str) -> dict[str, Any]:
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {
                "success": True,
                "transaction": "0xabc123",
                "payer": "0xPayer0000000000000000000000000000000001",
            },
        }

    monkeypatch.setattr(policy_check, "verify_and_settle", fake_settle)

    body = {
        "payment_required_header": _merchant_header(),
        "policy": {"allowed_networks": ["eip155:84532"], "max_amount_atomic": "10000000"},
        "idempotency_key": "idem-http-1",
    }
    r1 = client.post("/x402/policy-check", json=body, headers={"PAYMENT-SIGNATURE": "sig"})
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1.get("verdict") == "pass"
    assert j1.get("analysis_receipt", {}).get("digest_sha256")

    r2 = client.post("/x402/policy-check", json=body, headers={"PAYMENT-SIGNATURE": "sig2"})
    assert r2.status_code == 200
    assert r2.json() == j1

    body_conflict = dict(body)
    body_conflict["policy"] = {"allowed_networks": ["eip155:1"]}
    r3 = client.post(
        "/x402/policy-check",
        json=body_conflict,
        headers={"PAYMENT-SIGNATURE": "sig3", "Idempotency-Key": "idem-http-1"},
    )
    assert r3.status_code == 409
    assert r3.json().get("error") == "idempotency_conflict"


def test_redis_strict_idempotency_unavailable_503(
    policy_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "redis_url", "redis://fake-policy-check")
    monkeypatch.setattr(settings, "policy_check_idempotency_redis_strict", True)

    from app import redis_client

    monkeypatch.setattr(redis_client, "client", None)

    async def fake_settle(_sig: str, _hdr: str) -> dict[str, Any]:
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0x1", "payer": "0xp"},
        }

    monkeypatch.setattr(policy_check, "verify_and_settle", fake_settle)
    body = {
        "payment_required_header": _merchant_header(),
        "policy": {},
        "idempotency_key": "need-redis",
    }
    r = client.post("/x402/policy-check", json=body, headers={"PAYMENT-SIGNATURE": "s"})
    assert r.status_code == 503
    assert r.json().get("error") == "idempotency_store_unavailable"
