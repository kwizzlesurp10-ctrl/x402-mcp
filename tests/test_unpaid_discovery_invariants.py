"""Regression: unpaid discovery probes always get 402; paid bad input never settles."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from x402.extensions.bazaar import validate_discovery_extension
from x402.http import decode_payment_required_header

from app import openapi_spec
from app.agent_surface import paid_resources
from app.city_compliance import gate, registry
from app.config import settings
from app.main import app
from tests.discovery_unpaid import probe_unpaid_no_input

client = TestClient(app)

TEST_PAY_TO = "0xTestPayTo00000000000000000000000000000003"

SKIP_UNPAID_402 = {"/x402/policy-check"}  # env-gated


@pytest.fixture(autouse=True)
def _fresh_challenge_cache(monkeypatch):
    from app import challenge_cache

    challenge_cache.clear()
    monkeypatch.setattr(challenge_cache, "_load", lambda _name: None)
    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)
    yield
    challenge_cache.clear()


def _paid_http_probes() -> list[tuple[str, str]]:
    probes: list[tuple[str, str]] = []
    for resource in paid_resources():
        if resource.get("price") == "free":
            continue
        base = settings.public_base_url.rstrip("/")
        path = resource["url"].replace(base, "")
        if path.startswith("/swarm/products/"):
            continue
        if path in SKIP_UNPAID_402:
            continue
        method = resource.get("method", "GET")
        probes.append((path, method))
    assert probes, "expected paid HTTP resources"
    return probes


@pytest.mark.parametrize("path,method", _paid_http_probes())
def test_unpaid_no_input_returns_402_with_bazaar(path: str, method: str) -> None:
    response = probe_unpaid_no_input(client, path, method=method)
    if response.status_code == 503:
        pytest.skip(f"{path} seller challenge unavailable in this environment")
    assert response.status_code == 402, f"{method} {path} → {response.status_code}"
    header = response.headers.get("PAYMENT-REQUIRED")
    assert header, f"{path} missing PAYMENT-REQUIRED"
    pr = decode_payment_required_header(header)
    assert pr.extensions and "bazaar" in pr.extensions, path
    assert validate_discovery_extension(pr.extensions["bazaar"]).valid


@pytest.mark.parametrize("code", list(registry.public_codes()))
def test_paid_city_blank_address_422_before_settle(
    code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def must_not_settle(signature: str, payment_required: str) -> dict:
        raise AssertionError("settlement must not run for invalid paid input")

    monkeypatch.setattr(gate, "verify_and_settle", must_not_settle)
    response = client.get(
        f"/us/{code}/property-check",
        params={"address": "  "},
        headers={"PAYMENT-SIGNATURE": "sig-test"},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_address"


def test_paid_mn_blank_address_422_before_settle(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import mn_compliance

    async def must_not_settle(signature: str, payment_required: str) -> dict:
        raise AssertionError("settlement must not run for invalid paid input")

    monkeypatch.setattr(mn_compliance, "verify_and_settle", must_not_settle)
    response = client.get(
        "/mn/property-check",
        params={"address": ""},
        headers={"PAYMENT-SIGNATURE": "sig-test"},
    )
    assert response.status_code == 422


def test_openapi_paid_paths_match_catalog() -> None:
    """Guard that parametrized probes track the public paid surface."""
    catalog_paths = {p for p, _ in _paid_http_probes()}
    for path in openapi_spec.paid_paths():
        if path.startswith("/swarm/products/"):
            continue
        assert path in catalog_paths or path in SKIP_UNPAID_402, path
