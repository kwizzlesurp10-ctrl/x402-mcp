"""/llms.txt, /.well-known/x402, and A2A agent card — generated from config.

Every hand-written doc in this repo drifted (10 tools vs 16, $8.00 vs $0.05).
These are built from settings at request time, and the tests pin the property
that matters: the advertised prices ARE the config prices.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_well_known_x402_serves_the_live_prices() -> None:
    body = client.get("/.well-known/x402").json()

    by_name = {r["name"]: r for r in body["resource_details"]}
    assert by_name["Base tx decision"]["price"] == settings.tx_decision_price
    assert (
        by_name["Minneapolis rental compliance"]["price"]
        == settings.mn_property_check_price
    )
    assert body["challenge_header"] == "PAYMENT-REQUIRED"
    assert body["mcp"]["streamable_http"].endswith("/mcp/mcp")


def test_well_known_x402_matches_the_published_fan_out_schema() -> None:
    """x402scan's compat parser wants `version` and bare URL strings; ours
    served `x402_version` and objects, so the fallback document was
    unreadable to the one crawler it exists for."""
    body = client.get("/.well-known/x402").json()

    assert body["version"] == 1
    assert body["resources"] and all(
        isinstance(u, str) and u.startswith("http") for u in body["resources"]
    )
    detail_urls = {r["url"] for r in body["resource_details"] if r["price"] != "free"}
    assert set(body["resources"]) == detail_urls


def test_llms_txt_is_plain_text_with_live_prices() -> None:
    response = client.get("/llms.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert settings.tx_decision_price in response.text
    assert "PAYMENT-SIGNATURE" in response.text
    # Free MN sample is advertised so agents can verify quality before paying.
    assert "/mn/property-check/sample" in response.text
    # Canonical Visit / Resource URLs for Gold402 / 24K / scanners.
    base = settings.public_base_url.rstrip("/")
    assert f"{base}/us/cities" in response.text
    assert f"{base}/us/sea/property-check" in response.text
    assert f"{base}/us/sea/property-check/sample" in response.text


def test_llms_txt_documents_failure_modes_not_just_the_happy_path() -> None:
    text = client.get("/llms.txt").text

    for signal in ("502", "payment_invalid", "422", "staleness"):
        assert signal in text, f"missing failure-mode coverage: {signal}"


def test_the_advertised_endpoints_exist() -> None:
    """Every URL the manifest advertises must answer — no dead doors."""
    body = client.get("/.well-known/x402").json()

    for r in body["resource_details"]:
        path = r["url"].replace(settings.public_base_url.rstrip("/"), "")
        method = r.get("method", "GET")
        response = client.request(method, path)
        # Paid endpoints answer 402/422/503 unpaid; free ones 200. 404 = rot.
        assert response.status_code != 404, f"{path} advertised but missing"


def test_a_bare_probe_of_a_paid_endpoint_gets_the_challenge_not_a_422() -> None:
    """How every crawler and agent meets us: a probe with no parameters/body.

    `/mn/property-check` used to answer 422 here, because FastAPI's validation
    of a required `address` ran before any payment logic. "Expected 402, got
    400/422 from request validation running before the payment challenge" is on
    x402scan's published list of registration failures — and that endpoint has
    never been indexed by any catalog, while its 402-clean siblings both were.
    A paid door that answers anything but 402 is a door nobody can find.
    """
    body = client.get("/.well-known/x402").json()
    paid = [r for r in body["resource_details"] if r["price"] != "free"]
    assert paid, "no paid resources advertised"

    for r in paid:
        path = r["url"].replace(settings.public_base_url.rstrip("/"), "")
        method = r.get("method", "GET")
        response = client.request(method, path)  # unparameterised probe, exactly like a crawler
        if response.status_code == 503:
            continue  # seller not configured on this box; nothing to sell
        assert response.status_code == 402, (
            f"{path} answered {response.status_code} to an unparameterised {method} probe; "
            "a discovery crawler will mark it non-registerable"
        )
        assert "payment-required" in {k.lower() for k in response.headers}, (
            f"{path} returned 402 with no PAYMENT-REQUIRED header — an agent "
            "cannot pay a challenge it was never given"
        )


def test_agent_card_is_served_at_well_known() -> None:
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    body = response.json()
    assert body["name"]
    assert body["protocolVersion"] == "1.0"
    assert body["capabilities"]["streaming"] is False
    assert body["capabilities"]["pushNotifications"] is False
    assert any(s["id"] == "us-cities-catalog" for s in body["skills"])
    assert any(s["id"] == "us-city-property-check" for s in body["skills"])
    # Every live city in the registry is a skill for discovery ranking.
    from app.city_compliance import registry

    for code in registry.known_codes():
        assert any(s["id"] == f"property-check-{code}" for s in body["skills"]), code
    # Catalog URL is a supported interface.
    urls = [i["url"] for i in body["supportedInterfaces"]]
    assert any(u.endswith("/us/cities") for u in urls)
    # x402 is the declared payment scheme.
    assert "x402" in body["securitySchemes"]
    assert body["securitySchemes"]["x402"]["name"] == "PAYMENT-SIGNATURE"


def test_legacy_agent_json_mirrors_agent_card() -> None:
    card = client.get("/.well-known/agent-card.json").json()
    legacy = client.get("/.well-known/agent.json").json()
    assert legacy == card


def test_agent_card_skills_track_live_city_prices() -> None:
    """Skills must not hard-code prices that diverge from config/registry."""
    from app.city_compliance import registry

    body = client.get("/.well-known/agent-card.json").json()
    by_id = {s["id"]: s for s in body["skills"]}
    for entry in registry.list_cities():
        skill = by_id[f"property-check-{entry['code']}"]
        assert entry["price"] in skill["description"]
        assert entry["paid_url"] in skill["description"]
        assert entry["sample_url"] in skill["description"]


def test_llms_txt_advertises_a2a_agent_card() -> None:
    text = client.get("/llms.txt").text
    assert "/.well-known/agent-card.json" in text
    assert "/.well-known/funding.json" in text
    assert "/.well-known/agents.json" in text
    assert "payTo" in text or "payTo (settlement)" in text


def test_agents_json_served_at_well_known() -> None:
    response = client.get("/.well-known/agents.json")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0.0"
    assert "agents" in body
    assert len(body["agents"]) >= 3
    ids = {a["id"] for a in body["agents"]}
    assert "us-rental-diligence" in ids
    assert "base-tx-decision" in ids
    assert "us-city-compliance-network" in ids
    assert body["payment_networks"] == [settings.x402_default_network]
    assert body["settlement_address"]
    assert body["settlement_address"].lower().startswith("0x")


def test_mcp_server_card_served_at_well_known() -> None:
    response = client.get("/.well-known/mcp/server-card.json")
    assert response.status_code == 200
    body = response.json()
    assert body["serverInfo"]["name"] == "io.github.kwizzlesurp10-ctrl/x402-mcp"
    assert body["transport"]["type"] == "streamable-http"
    assert body["authentication"]["type"] == "x402"
    assert "tools" in body
    assert len(body["tools"]) >= 10
    assert body["authentication"]["pay_to"]


def test_funding_json_exposes_payto_and_bounties() -> None:
    response = client.get("/.well-known/funding.json")
    assert response.status_code == 200
    body = response.json()
    assert body["assetSymbol"] == "USDC"
    assert body["asset"].lower() == "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    assert body["payTo"].lower().startswith("0x")
    assert body["chainId"] == 8453
    assert "BOUNTIES.md" in body["bounties"]["protocol"]
    assert "not a token" in body["legal"].lower()
    assert body["discovery"]["agentCard"].endswith("/.well-known/agent-card.json")


def test_agent_card_declares_x402_extension_and_funding() -> None:
    body = client.get("/.well-known/agent-card.json").json()
    exts = body["capabilities"].get("extensions") or []
    assert any("a2a-x402" in (e.get("uri") or "") for e in exts)
    assert body["payments"]["rails"][0]["id"] == "x402"
    assert body["funding"]["payTo"]
    assert body["funding"]["assetSymbol"] == "USDC"


def test_well_known_x402_includes_payto() -> None:
    body = client.get("/.well-known/x402").json()
    assert body["payTo"].lower().startswith("0x")
    assert body["asset"].lower().endswith("2913")
    assert body["funding"].endswith("/.well-known/funding.json")

