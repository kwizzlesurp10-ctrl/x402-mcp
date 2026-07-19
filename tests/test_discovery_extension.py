"""Bazaar discoverability: 402 challenges must carry catalogable metadata.

Follows repo conventions: monkeypatch collaborators (the facilitator client is
faked so no network I/O happens), assert on the decoded PAYMENT-REQUIRED
header — the exact artifact a buyer's x402 client and the CDP facilitator see.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import x402_services
from app.config import settings
from app.models import BuildSellerRequirementsInput

TESTNET = "eip155:84532"
PAY_TO = "0x209693Bc6afc0C5328bA36FaF03C514EF312287C"


class _FakeFacilitator:
    """Offline stand-in advertising exact/eip155:84532 like x402.org."""

    def get_supported(self):
        from x402.schemas import SupportedKind, SupportedResponse

        return SupportedResponse(
            kinds=[SupportedKind(x402_version=2, scheme="exact", network=TESTNET)],
            extensions=["bazaar"],
        )


@pytest.fixture
def offline_facilitator(monkeypatch):
    monkeypatch.setattr(
        x402_services, "_facilitator_client", lambda network=None: _FakeFacilitator()
    )


def _decode(header: str):
    from x402.http import decode_payment_required_header

    return decode_payment_required_header(header)


def _build(**overrides) -> dict:
    params = {
        "network": TESTNET,
        "pay_to": PAY_TO,
        "price": "$0.05",
        "description": "Composite research report: zk rollups",
        **overrides,
    }
    return x402_services.build_seller_requirements(
        BuildSellerRequirementsInput(**params)
    )


PURCHASE_URL = "https://x402.example.com/swarm/products/abc123/purchase"


def test_402_header_carries_resource_and_bazaar_extension(offline_facilitator):
    result = _build(
        resource_url=PURCHASE_URL,
        discovery_method="GET",
        discovery_output_example={
            "product_id": "abc123",
            "topic": "zk rollups",
            "report": "# Composite research report",
            "payment_settled": True,
        },
    )

    assert result["discoverable"] is True
    assert result["resource"]["url"] == PURCHASE_URL

    pr = _decode(result["payment_required_header"])
    assert pr.resource is not None
    assert pr.resource.url == PURCHASE_URL
    assert pr.resource.description == "Composite research report: zk rollups"
    assert pr.resource.mime_type == "application/json"
    assert pr.resource.service_name == settings.bazaar_service_name.strip()[:32]
    assert pr.resource.tags  # <=5 tags from BAZAAR_SERVICE_TAGS
    assert len(pr.resource.tags) <= 5

    assert pr.extensions and "bazaar" in pr.extensions
    bazaar = pr.extensions["bazaar"]
    assert bazaar["info"]["input"]["type"] == "http"
    assert bazaar["info"]["input"]["method"] == "GET"
    assert bazaar["info"]["output"]["example"]["product_id"] == "abc123"

    # What the facilitator checks before cataloging: info validates
    # against the extension's own schema.
    from x402.extensions.bazaar import validate_discovery_extension

    validation = validate_discovery_extension(bazaar)
    assert validation.valid, validation.errors


def test_facilitator_extracts_discovery_info_at_settle_time(offline_facilitator):
    """Round-trip through the exact code path CDP runs when a payment settles:
    the buyer client copies PaymentRequired.extensions into PaymentPayload and
    the facilitator calls extract_discovery_info on it."""
    from x402.extensions.bazaar import extract_discovery_info
    from x402.schemas import PaymentPayload

    result = _build(
        resource_url=PURCHASE_URL,
        discovery_method="GET",
        discovery_output_example={"product_id": "abc123", "payment_settled": True},
    )
    pr = _decode(result["payment_required_header"])

    payload = PaymentPayload(
        payload={},
        accepted=pr.accepts[0],
        resource=pr.resource,
        extensions=pr.extensions,
    )
    discovered = extract_discovery_info(payload, pr.accepts[0])

    assert discovered is not None
    assert discovered.resource_url == PURCHASE_URL
    assert discovered.method == "GET"
    assert discovered.service_name == settings.bazaar_service_name.strip()[:32]


def test_post_method_builds_body_extension(offline_facilitator):
    result = _build(
        resource_url=PURCHASE_URL,
        discovery_method="POST",
        discovery_input_example={"agent_id": "buyer-1"},
        discovery_output_example={"payment_settled": True},
    )
    bazaar = _decode(result["payment_required_header"]).extensions["bazaar"]
    inp = bazaar["info"]["input"]
    assert inp["method"] == "POST"
    assert inp["bodyType"] == "json"
    assert inp["body"] == {"agent_id": "buyer-1"}

    from x402.extensions.bazaar import validate_discovery_extension

    assert validate_discovery_extension(bazaar).valid


def test_discoverable_false_omits_extension_keeps_resource(offline_facilitator):
    result = _build(resource_url=PURCHASE_URL, discoverable=False)
    assert result["discoverable"] is False
    pr = _decode(result["payment_required_header"])
    assert pr.extensions is None
    assert pr.resource is not None  # resource info still describes the endpoint


def test_settings_toggle_disables_discovery(offline_facilitator, monkeypatch):
    monkeypatch.setattr(settings, "bazaar_discoverable", False)
    result = _build(resource_url=PURCHASE_URL)  # discoverable=None -> setting
    assert result["discoverable"] is False
    assert _decode(result["payment_required_header"]).extensions is None


def test_long_description_clamped_to_cdp_limit(offline_facilitator):
    """CDP rejects verify+settle when a description exceeds the limit, so an
    over-long (e.g. user-topic-derived) description must be clamped on EVERY
    CDP-facing path: the accepts[].description, PaymentRequired.error, and the
    ResourceInfo.description."""
    long_topic = "zk rollups " * 80  # ~880 chars, well over the 500 limit
    result = _build(
        description=f"Composite research report: {long_topic}",
        resource_url=PURCHASE_URL,
        discovery_output_example={"payment_settled": True},
    )
    pr = _decode(result["payment_required_header"])
    limit = x402_services.CDP_MAX_DESCRIPTION_CHARS

    assert len(pr.error) <= limit
    assert pr.error.endswith("...")
    assert pr.resource is not None
    assert len(pr.resource.description) <= limit


def test_short_description_unchanged(offline_facilitator):
    result = _build(description="short and fine", resource_url=PURCHASE_URL)
    pr = _decode(result["payment_required_header"])
    assert pr.error == "short and fine"
    assert pr.resource.description == "short and fine"


def test_no_resource_url_is_backward_compatible(offline_facilitator):
    result = _build()
    assert result["discoverable"] is False
    assert result["resource"] is None
    pr = _decode(result["payment_required_header"])
    assert pr.resource is None
    assert pr.extensions is None
    assert len(pr.accepts) == 1  # challenge itself unchanged


def test_merchant_listing_is_discoverable(offline_facilitator, monkeypatch):
    """merchant_list threads product-derived discovery metadata through."""
    monkeypatch.setattr(settings, "x402_pay_to_address", PAY_TO)
    monkeypatch.setattr(settings, "public_base_url", "https://x402.example.com")

    from app.swarm import roles
    from app.swarm.models import CompositeProduct, SwarmRun

    product = CompositeProduct(
        product_id="prod-disc-1",
        topic="zk rollups",
        cost_basis_usdc=0.03,
        price_usdc=0.09,
        markup=3.0,
        network=TESTNET,
        sources=[],
        report="# Composite research report: zk rollups",
    )
    run = SwarmRun(
        run_id="run-disc-1",
        topic="zk rollups",
        agent_id="agent-disc",
        status="composing",
        started_ts="2026-07-16T00:00:00Z",
    )

    listed = roles.merchant_list(run, product, TESTNET)

    assert listed.seller_requirements["discoverable"] is True
    pr = _decode(listed.seller_requirements["payment_required_header"])
    assert (
        pr.resource.url
        == "https://x402.example.com/swarm/products/prod-disc-1/purchase"
    )
    bazaar = pr.extensions["bazaar"]
    assert bazaar["info"]["input"]["method"] == "GET"
    example = bazaar["info"]["output"]["example"]
    assert example["product_id"] == "prod-disc-1"
    assert example["payment_settled"] is True


def test_purchase_endpoint_serves_discoverable_402(offline_facilitator, monkeypatch):
    """GET /swarm/products/{id}/purchase serves the discovery-bearing header."""
    monkeypatch.setattr(settings, "x402_pay_to_address", PAY_TO)
    monkeypatch.setattr(settings, "public_base_url", "https://x402.example.com")

    from app.main import app
    from app.swarm import roles
    from app.swarm.models import CompositeProduct, SwarmRun
    from app.swarm.registry import swarm_registry

    product = CompositeProduct(
        product_id="prod-disc-http",
        topic="base pulse",
        cost_basis_usdc=0.0,
        price_usdc=0.25,
        markup=0.0,
        network=TESTNET,
        sources=[],
        report="# Base Network Pulse",
    )
    run = SwarmRun(
        run_id="run-disc-http",
        topic="base pulse",
        agent_id="agent-disc",
        status="composing",
        started_ts="2026-07-16T00:00:00Z",
    )
    roles.merchant_list(run, product, TESTNET)
    swarm_registry.list_product(product)

    client = TestClient(app)
    response = client.get("/swarm/products/prod-disc-http/purchase")

    assert response.status_code == 402
    header = response.headers.get("PAYMENT-REQUIRED")
    assert header
    pr = _decode(header)
    assert (
        pr.resource.url
        == "https://x402.example.com/swarm/products/prod-disc-http/purchase"
    )
    assert "bazaar" in pr.extensions
