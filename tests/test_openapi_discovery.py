"""`/openapi.json` is the document x402scan reads FIRST — it has to sell.

Before app/openapi_spec.py existed, FastAPI's generated spec told the largest
x402 explorer that this storefront had 33 routes and nothing for sale
(`L2_NO_PAID_ROUTES` from their own `@agentcash/discovery` auditor), and
published the operator surface while it was at it. These tests pin both halves:
every product is declared payable, and nothing operational is declared at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import agent_surface, openapi_spec
from app.config import settings
from app.main import app

client = TestClient(app)


@pytest.fixture
def spec() -> dict:
    return client.get("/openapi.json").json()


def test_every_paid_product_is_declared_payable(spec: dict) -> None:
    """The regression: a paid route the crawler cannot tell is paid."""
    paid = openapi_spec.paid_paths()
    assert paid, "no paid products resolved — the spec would advertise a free API"

    for path, amount in paid.items():
        operation = spec["paths"][path]["get"]
        info = operation["x-payment-info"]
        assert info["protocols"] == [{"x402": {}}]
        assert info["price"] == {"mode": "fixed", "currency": "USD", "amount": amount}
        assert "402" in operation["responses"]


def test_every_paid_endpoint_declares_an_input_an_agent_can_construct(spec: dict) -> None:
    """No declared inputs means "strict non-invocable" to x402scan — listed but
    skipped. The cataloged purchase URL has no query params at all once its
    product id is baked into the path, so the payment header is the input."""
    for path in openapi_spec.paid_paths():
        names = [p["name"] for p in spec["paths"][path]["get"].get("parameters", [])]
        assert names, f"{path} declares no inputs at all"
        assert "PAYMENT-SIGNATURE" in names, f"{path} does not document how to pay"


def test_every_paid_endpoint_says_what_you_get_for_your_money(spec: dict) -> None:
    """`agentcash check` reported `"outputSchema": {}` on three paid routes.

    The handlers return bare JSONResponse, so FastAPI emits a 200 whose schema
    is `{"type": "object", "additionalProperties": true}` — truthy, and
    describing nothing. An agent deciding whether to spend $0.01 could not see
    what it gets back, which is the whole question. Note this is a *different*
    field from the Bazaar extension's output schema in the runtime 402, which
    was always populated — checking that one is what hid this for a day.
    """
    for path in openapi_spec.paid_paths():
        content = (
            (spec["paths"][path]["get"]["responses"]["200"].get("content") or {})
            .get("application/json")
        ) or {}
        properties = (content.get("schema") or {}).get("properties") or {}
        assert properties, f"{path} does not describe its response body"
        assert content.get("example"), f"{path} has no worked response example"


def test_response_schemas_come_from_the_products_own_examples(spec: dict) -> None:
    """One example per product feeds both the OpenAPI schema and the Bazaar
    extension, so the two documents cannot describe different responses."""
    from app import tx_decision

    example = spec["paths"]["/base/tx-decision"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["example"]
    assert example == tx_decision.DISCOVERY_OUTPUT_EXAMPLE


def test_a_handler_that_documents_itself_is_left_alone() -> None:
    """Don't clobber a real response_model with an inferred schema."""
    real = {"type": "object", "properties": {"kept": {"type": "string"}}}
    operation = {
        "responses": {"200": {"content": {"application/json": {"schema": real}}}}
    }
    openapi_spec._declare_paid(operation, "0.01", {"inferred": 1})
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == real


@pytest.mark.parametrize(
    ("example", "expected"),
    [
        ({"a": "s"}, {"type": "object", "properties": {"a": {"type": "string"}}}),
        ({"n": 1}, {"type": "object", "properties": {"n": {"type": "integer"}}}),
        ({"f": 1.5}, {"type": "object", "properties": {"f": {"type": "number"}}}),
        ({"b": True}, {"type": "object", "properties": {"b": {"type": "boolean"}}}),
        ({"z": None}, {"type": "object", "properties": {"z": {}}}),
        (
            {"l": [{"k": "v"}]},
            {
                "type": "object",
                "properties": {
                    "l": {
                        "type": "array",
                        "items": {"type": "object", "properties": {"k": {"type": "string"}}},
                    }
                },
            },
        ),
    ],
)
def test_schema_inference(example: dict, expected: dict) -> None:
    # bool before int: True is an int in Python, and "boolean" is the honest type.
    assert openapi_spec._schema_from_example(example) == expected


def test_prices_are_decimal_usd_not_atomic_units(spec: dict) -> None:
    """Atomic units where dollars belong is on x402scan's published list of
    common registration failures ($0.01 is "0.01" here, "10000" on the wire)."""
    for path in openapi_spec.paid_paths():
        amount = spec["paths"][path]["get"]["x-payment-info"]["price"]["amount"]
        assert float(amount) < 100, f"{path} looks like atomic units: {amount}"
        assert not amount.startswith("$")


def test_the_paid_set_matches_the_other_discovery_documents(spec: dict) -> None:
    """One source of truth: adding a product to agent_surface must reach here."""
    from_surface = {
        openapi_spec._path_of(r["url"])
        for r in agent_surface.paid_resources()
        if r["price"] != "free"
    }
    declared = {p for p, o in spec["paths"].items() if "x-payment-info" in o.get("get", {})}
    assert from_surface <= declared, f"undeclared paid resources: {from_surface - declared}"


def test_the_operator_surface_is_not_published(spec: dict) -> None:
    leaked = [p for p in openapi_spec.OPERATOR_PATHS if p in spec["paths"]]
    assert not leaked, f"operator routes exposed in the public spec: {leaked}"


def test_a_new_route_is_private_by_default(spec: dict) -> None:
    """The allowlist has to fail closed — an unlisted route stays unlisted."""
    from fastapi.openapi.utils import get_openapi

    generated = set(
        get_openapi(title=app.title, version=app.version, routes=app.routes)["paths"]
    )
    published = set(spec["paths"])
    # Concrete product URLs FastAPI cannot express as templates: pinned Pulse
    # purchase id and per-city /us/{code}/property-check expansions.
    from app.city_compliance import registry as city_registry

    allowed_extra = {
        f"/swarm/products/{settings.pinned_pulse_product_id}/purchase",
        *(f"/us/{code}/property-check" for code in city_registry.known_codes()),
    }
    assert published - generated <= allowed_extra
    assert len(generated - published) > 15, "the spec published its whole inventory"


def test_free_routes_say_public_on_purpose(spec: dict) -> None:
    """`security: []` is the marker their auditor asks for; silence reads as an
    oversight and earns an AUTH_MODE_MISSING warning per route."""
    for path in openapi_spec.PUBLIC_FREE_PATHS:
        for operation in spec["paths"][path].values():
            assert operation.get("security") == [], f"{path} has no explicit auth mode"


def test_agents_get_the_payment_flow_without_reading_our_docs(spec: dict) -> None:
    guidance = spec["info"]["x-guidance"]
    assert "PAYMENT-REQUIRED" in guidance and "PAYMENT-SIGNATURE" in guidance
    assert "/llms.txt" in guidance
    # x402scan verifies ownership from the email specifically; a url alone does not.
    assert spec["info"]["contact"]["email"] == settings.contact_email
    assert "@" in spec["info"]["contact"]["email"]
    assert spec["info"]["contact"]["url"]
    assert spec["servers"][0]["url"] == settings.public_base_url.rstrip("/")


def test_the_cataloged_purchase_url_is_concrete_not_templated(spec: dict) -> None:
    """A crawler cannot probe `{product_id}`; only a real URL is registerable."""
    assert "/swarm/products/{product_id}/purchase" not in spec["paths"]
    if settings.pinned_pulse_product_id:
        concrete = f"/swarm/products/{settings.pinned_pulse_product_id}/purchase"
        assert concrete in spec["paths"]
        assert "product_id" not in str(spec["paths"][concrete]["get"].get("parameters", []))


def test_no_pinned_product_means_no_advertised_purchase_url(monkeypatch) -> None:
    """Advertising a listing that may not exist earns "expected 402, got 404"."""
    monkeypatch.setattr(settings, "pinned_pulse_product_id", "")
    assert not [p for p in openapi_spec.paid_paths() if p.endswith("/purchase")]


def test_an_unsigned_deployment_claims_no_ownership(spec: dict) -> None:
    """Absence means "not claimed yet"; an empty array reads as a failed proof."""
    if not settings.ownership_proofs:
        assert "x-discovery" not in spec
        assert "ownershipProofs" not in client.get("/.well-known/x402").json()


def test_a_signed_deployment_publishes_the_proof_in_both_documents(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ownership_proofs", "0xdeadbeef, 0xfeedface")

    assert client.get("/openapi.json").json()["x-discovery"] == {
        "ownershipProofs": ["0xdeadbeef", "0xfeedface"]
    }
    body = client.get("/.well-known/x402").json()
    assert body["ownershipProofs"] == ["0xdeadbeef", "0xfeedface"]


@pytest.mark.parametrize(
    ("price", "expected"),
    [("$0.01", "0.01"), ("0.05", "0.05"), ("free", None), ("", None), ("$x", None)],
)
def test_price_parsing(price: str, expected: str | None) -> None:
    assert openapi_spec._price_amount(price) == expected


def test_the_spec_follows_a_reprice_without_a_redeploy(monkeypatch, spec: dict) -> None:
    """Not cached on purpose — a stale spec quotes a price we no longer charge."""
    before = spec["paths"]["/base/tx-decision"]["get"]["x-payment-info"]["price"]["amount"]
    monkeypatch.setattr(settings, "tx_decision_price", "$0.99")
    after = client.get("/openapi.json").json()["paths"]["/base/tx-decision"]["get"][
        "x-payment-info"
    ]["price"]["amount"]
    assert before != after == "0.99"
