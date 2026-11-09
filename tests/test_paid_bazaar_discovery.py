"""Paid HTTP routes must ship invocable Bazaar + OpenAPI discovery metadata."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from x402.extensions.bazaar import validate_discovery_extension
from x402.http import decode_payment_required_header

from app import openapi_spec
from app.city_compliance import registry as city_registry
from app.config import settings
from app.discovery_schemas import bazaar_input_schema_has_properties
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_challenge_cache(monkeypatch):
    """Ignore Redis-backed challenge headers so 402s reflect current discovery schemas."""
    from app import challenge_cache

    challenge_cache.clear()
    monkeypatch.setattr(challenge_cache, "_load", lambda _name: None)
    yield
    challenge_cache.clear()


def _bazaar_from_402(path: str, *, method: str = "GET") -> dict:
    headers = {"x-demand-ignore": "1"}
    if method == "POST":
        response = client.post(path, headers=headers, json={})
    else:
        response = client.get(path, headers=headers)
    assert response.status_code == 402, f"{path} expected 402, got {response.status_code}"
    header = response.headers.get("PAYMENT-REQUIRED")
    assert header, f"{path} missing PAYMENT-REQUIRED"
    pr = decode_payment_required_header(header)
    assert pr.extensions and "bazaar" in pr.extensions, path
    return pr.extensions["bazaar"]


@pytest.mark.parametrize(
    "path",
    [
        "/mn/property-check",
        "/base/tx-decision",
        "/base/finality-check",
        "/agent/property-due-diligence",
        "/tasks/us-rental-diligence",
        *(f"/us/{code}/property-check" for code in city_registry.public_codes()),
    ],
)
def test_paid_http_402_bazaar_schema_is_populated(path: str) -> None:
    bazaar = _bazaar_from_402(path)
    validation = validate_discovery_extension(bazaar)
    assert validation.valid, validation.errors
    assert bazaar.get("schema"), path
    assert bazaar_input_schema_has_properties(bazaar), (
        f"{path} bazaar input schema has empty query/body properties"
    )


def test_policy_check_bazaar_schema_when_routed() -> None:
    if "/x402/policy-check" not in openapi_spec.paid_paths():
        pytest.skip("policy-check not in public paid surface")
    bazaar = _bazaar_from_402("/x402/policy-check", method="POST")
    assert validate_discovery_extension(bazaar).valid
    assert bazaar_input_schema_has_properties(bazaar)


def test_openapi_declares_x402_security_scheme() -> None:
    spec = client.get("/openapi.json").json()
    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    assert "x402" in schemes
    assert schemes["x402"]["name"] == "PAYMENT-SIGNATURE"


def test_openapi_city_summaries_are_per_city() -> None:
    spec = client.get("/openapi.json").json()
    for code in city_registry.public_codes():
        path = f"/us/{code}/property-check"
        if path not in spec["paths"]:
            continue
        op = spec["paths"][path]["get"]
        expected = city_registry.get_city(code).SPEC.service_name
        assert op.get("summary") == expected, path
        params = [p["name"] for p in op.get("parameters", [])]
        assert "address" in params, path


def test_homepage_catalog_mn_price_matches_config() -> None:
    from app.city_compliance import gate

    mn = city_registry.get_city("mn")
    assert gate.price_for(mn.SPEC) == settings.mn_property_check_price
