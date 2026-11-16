"""San Diego (sd) property-check: upstream source + verify-before-settle."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.city_compliance import gate, registry
from app.city_compliance.cities import sd as sd_city
from app.config import settings
from app.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "x402_pay_to_address", "0x" + "ab" * 20)
    monkeypatch.setattr(settings, "public_base_url", "http://test")
    return TestClient(app)


@pytest.mark.asyncio
async def test_sd_check_property_happy_path_from_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_rows() -> list[dict[str, str]]:
        return [
            {
                "license_id": "STR-TEST01",
                "address": "123 MAIN St, SAN DIEGO, CA 92101",
                "tier": "Tier 3",
                "date_expiration": "2028-01-01",
                "zip": "92101",
                "community_planning_area": "DOWNTOWN",
            }
        ]

    monkeypatch.setattr(sd_city, "_load_license_rows", fake_rows)
    sd_city._query_cache.clear()
    sd_city._csv_cache = None

    report = await sd_city.check_property("123 MAIN ST")
    assert report["compliance_verdict"] == "str_licensed_active"
    assert report["registrations"][0]["license_number"] == "STR-TEST01"
    assert sd_city.STRO_CSV_URL in report["sources"]


def test_sd_sample_returns_200_with_mocked_upstream(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_check(address: str) -> dict[str, Any]:
        return {
            "city": "sd",
            "address_queried": address,
            "compliance_verdict": "str_unlicensed",
            "registrations": [],
            "violation_cases": {"total": 0, "recent": []},
        }

    monkeypatch.setattr(registry.get_city("sd"), "check_property", fake_check)
    res = client.get("/us/sd/property-check/sample")
    assert res.status_code == 200
    assert res.json()["report"]["compliance_verdict"] == "str_unlicensed"


def test_sd_paid_upstream_failure_does_not_settle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settle_called = False

    async def fake_verify(signature: str, payment_required: str) -> dict:
        return {"is_valid": True, "invalid_reason": None}

    async def must_not_settle(signature: str, payment_required: str) -> dict:
        nonlocal settle_called
        settle_called = True
        raise AssertionError("settle must not run when upstream fails")

    async def boom(address: str) -> dict[str, Any]:
        raise TimeoutError("upstream down")

    monkeypatch.setattr(gate, "build_payment_required_header", lambda *a, **k: "pr-hdr")
    monkeypatch.setattr(gate, "verify_payment", fake_verify)
    monkeypatch.setattr(gate, "settle_payment", must_not_settle)
    monkeypatch.setattr(registry.get_city("sd"), "check_property", boom)

    res = client.get(
        "/us/sd/property-check",
        params={"address": "123 MAIN ST"},
        headers={"PAYMENT-SIGNATURE": "sig-test"},
    )
    assert res.status_code == 503
    body = res.json()
    assert body["error"] == "upstream_open_data_unavailable"
    assert body.get("payment_settled") is False
    assert res.headers.get("payment-response") is None
    assert settle_called is False


def test_sd_paid_happy_path_settles_after_fetch(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def fake_verify(signature: str, payment_required: str) -> dict:
        calls.append("verify")
        return {"is_valid": True}

    async def fake_settle(signature: str, payment_required: str) -> dict:
        calls.append("settle")
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0xabc"},
        }

    async def fake_check(address: str) -> dict[str, Any]:
        calls.append("fetch")
        return {
            "city": "sd",
            "address_queried": address,
            "compliance_verdict": "str_unlicensed",
            "registrations": [],
            "violation_cases": {"total": 0, "recent": []},
        }

    monkeypatch.setattr(gate, "build_payment_required_header", lambda *a, **k: "pr-hdr")
    monkeypatch.setattr(gate, "verify_payment", fake_verify)
    monkeypatch.setattr(gate, "settle_payment", fake_settle)
    monkeypatch.setattr(registry.get_city("sd"), "check_property", fake_check)

    res = client.get(
        "/us/sd/property-check",
        params={"address": "999 UNKNOWN AVE"},
        headers={"PAYMENT-SIGNATURE": "sig-test"},
    )
    assert res.status_code == 200
    assert calls == ["verify", "fetch", "settle"]
    assert res.headers.get("payment-response")