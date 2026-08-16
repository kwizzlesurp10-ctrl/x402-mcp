"""Seller demo revenue path: /demo/paid, /demo/paid/info, /ops/status.

These endpoints build a 402 challenge, verify+settle a buyer payment, and write
a revenue ledger row, so they need the same guards the sibling seller repo
learned to keep: unpaid is always 402 (never 500), the challenge is cached with
a fingerprint covering every input, and the advertised resource URL cannot be
chosen by the caller.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import challenge_cache, main as main_mod
from app.config import settings
from app.main import app

client = TestClient(app)

PAY_TO = "0xAB745e5F576667037696e78ba7dA28E193E4423D"


@pytest.fixture(autouse=True)
def _clean_cache():
    challenge_cache.clear()
    main_mod._demo_paid_built.clear()
    yield
    challenge_cache.clear()
    main_mod._demo_paid_built.clear()


@pytest.fixture
def seller_configured(monkeypatch):
    monkeypatch.setattr(settings, "x402_pay_to_address", PAY_TO)
    return PAY_TO


# ---------- unpaid path ----------


def test_unpaid_request_is_402_with_payment_required_header(seller_configured) -> None:
    response = client.get("/demo/paid")
    assert response.status_code == 402
    assert response.headers.get("PAYMENT-REQUIRED")


def test_challenge_build_failure_is_503_not_500(monkeypatch, seller_configured) -> None:
    """A facilitator outage must not make this endpoint look non-compliant.

    Indexers record a non-402 response as a failure; a 500 gets the resource
    dropped from catalogs, a retryable 503 does not.
    """
    from app import x402_services

    async def _boom(**_kwargs):
        raise RuntimeError("facilitator down")

    monkeypatch.setattr(x402_services, "build_payment_required_for_resource", _boom)

    response = client.get("/demo/paid")
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "30"
    assert response.json()["error"] == "challenge_unavailable"


def test_challenge_is_cached_across_requests(monkeypatch, seller_configured) -> None:
    """Crawlers hammer the unpaid path; it must not cost a facilitator call each."""
    from app import x402_services

    calls = {"n": 0}
    real = x402_services.build_payment_required_for_resource

    async def _counted(**kwargs):
        calls["n"] += 1
        return await real(**kwargs)

    monkeypatch.setattr(x402_services, "build_payment_required_for_resource", _counted)

    assert client.get("/demo/paid").status_code == 402
    assert client.get("/demo/paid").status_code == 402
    assert calls["n"] == 1


# ---------- the fingerprint lesson ----------


def test_fingerprint_changes_when_description_changes() -> None:
    """A description that is baked into the header must bust the cache.

    The sibling repo shipped a rewritten catalog description that deployed
    cleanly and never reached a buyer, because the fingerprint did not cover it
    and a catalog indexes the description exactly once.
    """
    base = dict(resource_url="https://x/demo", price="$0.01", network="eip155:84532")
    a = challenge_cache.fingerprint(**base, description="old text")
    b = challenge_cache.fingerprint(**base, description="new text")
    assert a != b


def test_fingerprint_is_stable_for_identical_inputs() -> None:
    parts = dict(resource_url="https://x/demo", description="d", price="$0.01")
    assert challenge_cache.fingerprint(**parts) == challenge_cache.fingerprint(**parts)


def test_stale_challenge_is_served_when_rebuild_fails() -> None:
    """A stale 402 beats no 402 (current API: name + fingerprint + sync builder)."""
    calls = {"n": 0}

    def _builder() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "good"
        raise RuntimeError("facilitator down")

    first = challenge_cache.get_or_build("demo-stale", "fp-a", _builder)
    # Different fingerprint forces a rebuild attempt; failure serves last-known-good.
    second = challenge_cache.get_or_build("demo-stale", "fp-b", _builder)

    assert first == "good"
    assert second == "good"
    assert calls["n"] == 2


def test_cold_start_failure_propagates() -> None:
    """With nothing cached there is nothing honest to serve — the caller 503s."""

    def _builder() -> str:
        raise RuntimeError("facilitator down")

    with pytest.raises(RuntimeError):
        challenge_cache.get_or_build("demo-cold", "fp-cold", _builder)


# ---------- advertised resource URL ----------


def test_forwarded_host_is_ignored_by_default(monkeypatch, seller_configured) -> None:
    """The resource URL is signed into the challenge and indexed once."""
    monkeypatch.setattr(settings, "trust_forwarded_host", False)
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8402")

    response = client.get("/demo/paid/info", headers={"X-Forwarded-Host": "evil.example"})
    assert response.status_code == 200
    assert response.json()["resource"] == "http://localhost:8402/demo/paid"


def test_forwarded_host_is_honoured_when_trusted(monkeypatch, seller_configured) -> None:
    monkeypatch.setattr(settings, "trust_forwarded_host", True)

    response = client.get(
        "/demo/paid/info",
        headers={"X-Forwarded-Host": "demo.example", "X-Forwarded-Proto": "https"},
    )
    assert response.json()["resource"] == "https://demo.example/demo/paid"


def test_trusted_forwarded_loopback_falls_back_to_config(monkeypatch, seller_configured) -> None:
    monkeypatch.setattr(settings, "trust_forwarded_host", True)
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8402")

    response = client.get("/demo/paid/info", headers={"X-Forwarded-Host": "[::1]:8402"})
    assert response.json()["resource"] == "http://localhost:8402/demo/paid"


# ---------- CORS ----------


def test_arbitrary_tunnel_origin_is_not_allowed() -> None:
    """Anyone can register a free tunnel subdomain, and this API has no auth."""
    response = client.get(
        "/health", headers={"Origin": "https://attacker.trycloudflare.com"}
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in {
        k.lower() for k in response.headers.keys()
    }


def test_local_dev_origin_is_allowed() -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


# ---------- free metadata surfaces ----------


def test_demo_paid_info_is_free_and_describes_the_flow(seller_configured) -> None:
    body = client.get("/demo/paid/info").json()
    assert body["price"] == settings.x402_default_price
    assert body["network"] == settings.x402_default_network
    assert len(body["flow"]) == 3


def test_ops_status_reports_doctor_checks() -> None:
    response = client.get("/ops/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "x402-micropayments-mcp"
    assert isinstance(body["checks"], list)
    assert "doctor_ok" in body
