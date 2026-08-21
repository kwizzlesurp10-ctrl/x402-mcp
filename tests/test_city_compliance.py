"""US City Open-Data Compliance Network — catalog, 402 gate, samples."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.city_compliance import registry
from app.config import settings
from app.main import app

client = TestClient(app)

TEST_PAY_TO = "0xTestPayTo00000000000000000000000000000002"


def test_us_cities_catalog_lists_mn_and_peers() -> None:
    response = client.get("/us/cities")
    assert response.status_code == 200
    body = response.json()
    assert body["network"] == "us-city-open-data-compliance"
    codes = {c["code"] for c in body["cities"]}
    assert codes == set(registry.known_codes())
    assert "mn" in codes and "nola" in codes and "moco" in codes
    mn = next(c for c in body["cities"] if c["code"] == "mn")
    assert mn["state"] == "MN"
    assert mn["canonical_alias"] == "/mn/property-check"
    assert mn["paid_url"].endswith("/us/mn/property-check")


def test_unknown_city_404() -> None:
    response = client.get("/us/atl/property-check")
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_city"
    assert "mn" in response.json()["known"]


@pytest.mark.parametrize("code", list(registry.known_codes()))
def test_unpaid_city_always_402_before_address_validation(
    code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)
    for params in ({}, {"address": "   "}):
        response = client.get(f"/us/{code}/property-check", params=params)
        assert response.status_code == 402, (code, params)
        assert "PAYMENT-REQUIRED" in response.headers
        body = response.json()
        assert body["error"] == "payment_required"
        assert body["city"] == code
        assert body["sample_url"].endswith(f"/us/{code}/property-check/sample")


@pytest.mark.parametrize("code", list(registry.known_codes()))
def test_paid_blank_address_rejected_before_settle(
    code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.city_compliance import gate

    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)

    async def must_not_settle(signature: str, payment_required: str) -> dict:
        raise AssertionError("settlement attempted for invalid address")

    monkeypatch.setattr(gate, "verify_and_settle", must_not_settle)
    response = client.get(
        f"/us/{code}/property-check",
        params={"address": "   "},
        headers={"PAYMENT-SIGNATURE": "sig-abc"},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_address"


def test_malformed_signature_on_city_path_is_402_not_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)
    response = client.get(
        "/us/sea/property-check",
        params={"address": "1531 BELMONT AVE"},
        headers={"PAYMENT-SIGNATURE": "e30="},
    )
    assert response.status_code == 402
    assert response.json()["error"] == "payment_invalid"


@pytest.mark.parametrize("code", list(registry.known_codes()))
def test_sample_does_not_require_payment(
    code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = registry.get_city(code)
    sample = mod.SPEC.sample_address

    async def fake_report(address: str) -> dict:
        assert address == sample
        return {
            "city": code,
            "address_queried": address,
            "compliance_verdict": "sample_ok",
            "registrations": [],
            "registered": False,
            "violation_cases": {"total": 0, "recent": []},
            "network_product": "us-city-open-data-compliance",
        }

    monkeypatch.setattr(mod, "check_property", fake_report)
    response = client.get(f"/us/{code}/property-check/sample")
    assert response.status_code == 200
    body = response.json()
    assert body["sample"] is True
    assert body["city"] == code
    assert body["sample_address"] == sample
    assert body["price"] == settings.city_network_price
    assert body["report"]["compliance_verdict"] == "sample_ok"


def test_mn_network_path_delegates_to_mn_compliance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network /us/mn wraps mn_compliance; does not reimplement ArcGIS."""
    from app.city_compliance.cities import mn as mn_city
    from app import mn_compliance

    async def fake_mn(address: str) -> dict:
        return {
            "address_queried": address,
            "compliance_verdict": "licensed_clean",
            "licensed": True,
            "rental_licenses": [{"license_number": "LIC1", "address": address}],
            "violation_cases": {"total": 0, "recent": []},
            "condemned_or_boarded": {"flagged": False, "records": []},
            "sources": ["https://example.test/arcgis"],
            "disclaimer": "test",
            "generated_at": "2026-08-06T00:00:00+00:00",
        }

    monkeypatch.setattr(mn_compliance, "check_property", fake_mn)
    import asyncio

    report = asyncio.run(mn_city.check_property("1700 Penn Ave N"))
    assert report["city"] == "mn"
    assert report["state"] == "MN"
    assert report["compliance_verdict"] == "licensed_clean"
    assert report["canonical_resource"] == "/mn/property-check"
    assert report["registrations"][0]["license_number"] == "LIC1"
