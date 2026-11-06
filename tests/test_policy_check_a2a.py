"""A2A skill `buyer-payment-policy-check` unpaid + paid (mocked verify_and_settle)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from x402.http import encode_payment_required_header
from x402.schemas import PaymentRequired, PaymentRequirements

from app import policy_check
from app.agent_surface import A2A_X402_EXTENSION_URI
from app.a2a_rpc import META_REQUIRED, META_STATUS, clear_task_store
from app.config import settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_tasks() -> None:
    clear_task_store()
    yield
    clear_task_store()


def _merchant_header() -> str:
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x3333333333333333333333333333333333333333",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="4000",
        max_timeout_seconds=300,
        extra={},
    )
    return encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="inspected")
    )


@pytest.fixture
def policy_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "policy_check_enabled", True)
    assert settings.x402_pay_to_address


def test_a2a_policy_check_unpaid_input_required(policy_on: None) -> None:
    start = client.post(
        "/a2a",
        headers={"X-A2A-Extensions": A2A_X402_EXTENSION_URI},
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [],
                    "metadata": {
                        "skillId": "buyer-payment-policy-check",
                        "input": {
                            "payment_required_header": _merchant_header(),
                            "policy": {"allowed_networks": ["eip155:84532"]},
                        },
                    },
                }
            },
        },
    )
    assert start.status_code == 200
    task = start.json()["result"]
    assert task["status"]["state"] == "input-required"
    meta = task["status"]["message"]["metadata"]
    assert meta[META_STATUS] == "payment-required"
    assert meta["x402.payment.required"]["x402Version"] == 2


@pytest.mark.asyncio
async def test_a2a_policy_check_paid_completes(policy_on: None, monkeypatch: pytest.MonkeyPatch) -> None:
    policy_check.clear_idempotency_test()

    async def fake_settle(_sig: str, _hdr: str) -> dict[str, Any]:
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {
                "success": True,
                "transaction": "0xa2apc01",
                "payer": "0xpayer00000000000000000000000000000002",
            },
        }

    monkeypatch.setattr(policy_check, "verify_and_settle", fake_settle)

    start = client.post(
        "/a2a",
        headers={"X-A2A-Extensions": A2A_X402_EXTENSION_URI},
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [],
                    "metadata": {
                        "skillId": "buyer-payment-policy-check",
                        "input": {
                            "payment_required_header": _merchant_header(),
                            "policy": {"allowed_networks": ["eip155:84532"], "max_amount_atomic": "10000000"},
                        },
                    },
                }
            },
        },
    )
    res = start.json()["result"]
    tid = res["id"]
    cap = res["capabilityToken"]
    required = res["status"]["message"]["metadata"][META_REQUIRED]
    accept_dict = required["accepts"][0]
    body = {
        "x402Version": 2,
        "payload": {"signature": "0xsig", "authorization": {}},
        "accepted": accept_dict,
    }
    from app.a2a_rpc import META_PAYLOAD, META_TASK_CAPABILITY

    pay = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [],
                    "taskId": tid,
                    "metadata": {
                        META_STATUS: "payment-submitted",
                        META_TASK_CAPABILITY: cap,
                        META_PAYLOAD: body,
                    },
                }
            },
        },
    )
    assert pay.status_code == 200
    done = pay.json()["result"]
    assert done["status"]["state"] == "completed"
    arts = done.get("artifacts") or []
    assert arts
    data = arts[0]["parts"][0]["data"]
    assert data.get("verdict") == "pass"
