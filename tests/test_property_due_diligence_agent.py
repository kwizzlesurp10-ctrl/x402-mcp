"""Tests for $0.01 property due diligence agent discovery product."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import property_due_diligence_agent as agent
from app.config import settings
from app.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "x402_pay_to_address", "0x" + "ab" * 20)
    monkeypatch.setattr(settings, "public_base_url", "http://test")
    monkeypatch.setattr(settings, "bazaar_discoverable", True)
    return TestClient(app)


def test_metadata_cdp_ceilings() -> None:
    assert len(agent.SERVICE_NAME) <= 32
    assert len(agent.SERVICE_TAGS) <= 5
    assert all(len(t) <= 32 for t in agent.SERVICE_TAGS)
    assert len(agent.RESOURCE_DESCRIPTION) <= 500
    low = agent.RESOURCE_DESCRIPTION.lower()
    assert "property due diligence agent" in low
    assert "housing compliance open data" in low
    assert agent.PRICE == "$0.01"


def test_get_402_without_payment(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent,
        "build_payment_required_header",
        lambda: "hdr",
    )
    r = client.get("/agent/property-due-diligence")
    assert r.status_code == 402
    assert r.headers.get("payment-required") == "hdr"
    body = r.json()
    assert body["product_id"] == agent.PRODUCT_ID
    assert body["price"] == "$0.01"
    assert "property due diligence agent" in body["description"].lower()


def test_paid_path_validates_args(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "build_payment_required_header", lambda: "hdr")

    async def _fake_settle(*_a, **_k):
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"transaction": "0xabc"},
        }

    async def _fake_check(*, city_code: str, address: str):
        return {
            "product_id": agent.PRODUCT_ID,
            "city": city_code,
            "address_queried": address,
            "compliance_verdict": "licensed_clean",
            "payment_settled": True,
            "agent": "property-due-diligence",
        }

    monkeypatch.setattr(agent, "verify_and_settle", _fake_settle)
    monkeypatch.setattr(agent, "run_check", _fake_check)

    r = client.get(
        "/agent/property-due-diligence",
        headers={"PAYMENT-SIGNATURE": "sig"},
    )
    assert r.status_code == 422

    r2 = client.get(
        "/agent/property-due-diligence",
        params={"city_code": "mn", "address": "1700 Penn Ave N"},
        headers={"PAYMENT-SIGNATURE": "sig"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["compliance_verdict"] == "licensed_clean"
    assert body["agent"] == "property-due-diligence"
