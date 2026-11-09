"""PR #797 follow-up: OpenAPI required params, validate-before-402, CORS, agent card."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import agent_surface, challenge_cache, openapi_spec
from app.city_compliance import registry
from app.config import settings
from app.discovery_schemas import bazaar_output_schema_has_properties
from app.main import app
from x402.http import decode_payment_required_header
from x402.extensions.bazaar import validate_discovery_extension

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_challenge_cache(monkeypatch):
    from app import challenge_cache as cc

    cc.clear()
    monkeypatch.setattr(cc, "_load", lambda _name: None)
    yield
    cc.clear()


def test_openapi_address_query_required_non_nullable() -> None:
    spec = client.get("/openapi.json").json()
    for path in ("/mn/property-check", "/us/sea/property-check"):
        param = next(
            p
            for p in spec["paths"][path]["get"]["parameters"]
            if p["name"] == "address"
        )
        assert param["required"] is True
        schema = param["schema"]
        assert schema.get("type") == "string"
        assert "anyOf" not in schema
        assert "null" not in str(schema.get("type", ""))


def test_openapi_diligence_post_request_body_only_on_post() -> None:
    spec = client.get("/openapi.json").json()
    ops = spec["paths"]["/tasks/us-rental-diligence"]
    assert "requestBody" not in ops.get("get", {})
    post = ops["post"]
    schema = post["requestBody"]["content"]["application/json"]["schema"]
    assert "properties" in schema
    assert "properties" in schema["properties"]


def test_unpaid_missing_address_returns_422_not_402() -> None:
    r = client.get(
        "/mn/property-check",
        headers={"x-demand-ignore": "1"},
    )
    assert r.status_code == 422
    assert r.json().get("schema", {}).get("openapi", "").startswith("/openapi.json")


def test_unpaid_city_missing_address_422() -> None:
    code = registry.public_codes()[0]
    r = client.get(
        f"/us/{code}/property-check",
        headers={"x-demand-ignore": "1"},
    )
    assert r.status_code == 422


def test_unpaid_diligence_empty_body_422() -> None:
    r = client.post(
        "/tasks/us-rental-diligence",
        headers={"x-demand-ignore": "1", "Content-Type": "application/json"},
        json={},
    )
    assert r.status_code == 422


def test_unpaid_finality_missing_tx_422() -> None:
    if not settings.x402_pay_to_address:
        pytest.skip("seller not configured")
    r = client.get(
        "/base/finality-check",
        headers={"x-demand-ignore": "1"},
    )
    assert r.status_code == 422


def test_well_formed_unpaid_city_still_402() -> None:
    mod = registry.get_city("sea")
    addr = mod.SPEC.sample_address
    r = client.get(
        f"/us/sea/property-check",
        params={"address": addr},
        headers={"x-demand-ignore": "1"},
    )
    assert r.status_code == 402
    assert r.headers.get("PAYMENT-REQUIRED")


def test_agent_card_paid_skills_have_input_schema() -> None:
    card = client.get("/.well-known/agent-card.json").json()
    paid = [
        sk
        for sk in card["skills"]
        if (sk.get("x402") or {}).get("paid") and sk["id"] not in ("x402-agent-card",)
    ]
    assert paid, "expected paid skills"
    missing = [sk["id"] for sk in paid if not sk.get("inputSchema")]
    assert not missing, f"skills missing inputSchema: {missing}"


def test_tx_decision_402_resource_service_name() -> None:
    from app import tx_decision

    r = client.get(
        "/base/tx-decision",
        params={"gas": "usdc", "urgency": "flexible"},
        headers={"x-demand-ignore": "1"},
    )
    assert r.status_code == 402
    pr = decode_payment_required_header(r.headers["PAYMENT-REQUIRED"])
    assert pr.resource is not None
    assert pr.resource.service_name == tx_decision.SERVICE_NAME


def test_pdd_description_lists_all_public_cities() -> None:
    from app import property_due_diligence_agent as pdd

    text = pdd.resource_description()
    for code in registry.public_codes():
        assert re.search(rf"\b{re.escape(code)}\b", text)


def test_discovery_cors_402_and_options() -> None:
    mod = registry.get_city("mn")
    r = client.get(
        "/mn/property-check",
        params={"address": mod.SPEC.sample_address},
        headers={
            "x-demand-ignore": "1",
            "Origin": "https://www.x402scan.com",
        },
    )
    assert r.status_code == 402
    assert r.headers.get("access-control-allow-origin") == "*"
    assert "PAYMENT-REQUIRED" in (r.headers.get("access-control-expose-headers") or "")

    opt = client.options(
        "/openapi.json",
        headers={
            "Origin": "https://www.x402scan.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert opt.status_code == 204
    assert opt.headers.get("access-control-allow-origin") == "*"


def test_well_known_lists_swarm_purchase_when_listed(monkeypatch) -> None:
    from app.swarm.models import CompositeProduct
    from app.swarm.registry import swarm_registry

    pid = "test-listing-05-pr797"
    product = CompositeProduct(
        product_id=pid,
        topic="test swarm composite",
        cost_basis_usdc=0.01,
        price_usdc=0.05,
        markup=5.0,
        network=settings.x402_default_network,
        sources=[],
        report="# test",
        status="listed",
        seller_requirements={
            "payment_required_header": "eA==",
            "price": "$0.05",
            "discoverable": True,
        },
    )
    try:
        swarm_registry.list_product(product)
        urls = agent_surface.well_known_x402()["resources"]
        assert (
            f"{settings.public_base_url.rstrip('/')}/swarm/products/{pid}/purchase"
            in urls
        )
    finally:
        swarm_registry._products.pop(pid, None)


def test_bazaar_output_schema_not_generic() -> None:
    mod = registry.get_city("mn")
    r = client.get(
        "/mn/property-check",
        params={"address": mod.SPEC.sample_address},
        headers={"x-demand-ignore": "1"},
    )
    bazaar = decode_payment_required_header(r.headers["PAYMENT-REQUIRED"]).extensions[
        "bazaar"
    ]
    assert validate_discovery_extension(bazaar).valid
    assert bazaar_output_schema_has_properties(bazaar)


def test_challenge_fingerprint_includes_cache_version() -> None:
    fp = challenge_cache.fingerprint(network="n", price="$0.01")
    assert challenge_cache.CHALLENGE_CACHE_VERSION >= 3


def test_robots_txt_allows_discovery() -> None:
    text = client.get("/robots.txt").text
    assert "Allow: /.well-known/" in text
    assert "Allow: /openapi.json" in text
