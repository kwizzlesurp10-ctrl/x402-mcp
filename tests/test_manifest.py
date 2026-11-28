"""Manifest and HTTP endpoint tests."""

from fastapi.testclient import TestClient

from app.main import app
from app.tools_registry import EXPECTED_TOOL_NAMES, TOOL_COUNT


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "x402-micropayments-mcp"
    assert isinstance(body["wallet_configured"], bool)
    assert isinstance(body["pay_to_configured"], bool)


def test_well_known_mcp_json_alias() -> None:
    a = client.get("/.well-known/mcp")
    b = client.get("/.well-known/mcp.json")
    assert a.status_code == 200
    assert b.status_code == 200
    assert a.json() == b.json()


def test_get_a2a_returns_agent_card() -> None:
    response = client.get("/a2a")
    assert response.status_code == 200
    card = response.json()
    assert card.get("name")
    assert card.get("protocolVersion") or card.get("skills")


def test_cities_alias_redirects() -> None:
    response = client.get("/cities", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].endswith("/us/cities")


def test_well_known_mcp() -> None:
    response = client.get("/.well-known/mcp")
    assert response.status_code == 200
    manifest = response.json()

    assert manifest["name"] == "x402-micropayments"
    assert manifest["protocol"] == "mcp"
    assert "free" in manifest["tiers"]
    assert manifest["tiers"]["free"]["monthly_quota"] == 500
    assert manifest["tiers"]["free"]["rate_limit_per_minute"] == 10
    assert manifest["upgrade_url"]
    assert len(manifest["tools"]) == TOOL_COUNT
    tool_names = {t["name"] for t in manifest["tools"]}
    assert tool_names == EXPECTED_TOOL_NAMES
    assert manifest["tiers"]["pro"]["payment_tools"]
    assert manifest["x402"]["protocol_version"] == "v2"
    assert "PAYMENT-REQUIRED" in manifest["x402"]["headers"]["payment_required"]


def test_quota_peek_no_consume(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "operator_token", "op-test")
    auth = {"Authorization": "Bearer op-test"}
    agent = "peek-agent-unique"
    first = client.get(f"/quota/{agent}", headers=auth).json()
    second = client.get(f"/quota/{agent}", headers=auth).json()
    assert first["meta"]["calls_this_month"] == second["meta"]["calls_this_month"]


def test_upgrade_endpoint() -> None:
    response = client.get("/upgrade")
    assert response.status_code == 200
    body = response.json()
    assert body["upgrade_url"]
    assert "pro" in body["tiers"]
    assert body["x402_coinbase"]["status"] == "primary_rail"
    assert "commerce.credits_requirements" in body["mcp_tools"]["tool_credits_x402"]
    assert body["tool_credits"]["pack_size"] == 100
    assert body["manifest"] == "/.well-known/mcp"


def test_manifest_payment_rails() -> None:
    manifest = client.get("/.well-known/mcp").json()
    assert manifest["payment_rails"]["x402_coinbase"]["primary"] is True


def test_well_known_mcp_json_alias() -> None:
    dotted = client.get("/.well-known/mcp.json")
    bare = client.get("/.well-known/mcp")
    assert dotted.status_code == 200
    assert dotted.json()["name"] == bare.json()["name"]


def test_get_a2a_returns_agent_card() -> None:
    response = client.get("/a2a")
    assert response.status_code == 200
    card = response.json()
    assert card.get("name")
    assert "/a2a" in str(card.get("url") or "")


def test_cities_alias_redirects_to_us_cities() -> None:
    response = client.get("/cities", follow_redirects=False)
    assert response.status_code in (307, 308)
    assert response.headers["location"].rstrip("/").endswith("/us/cities")


def test_well_known_x402_json_alias() -> None:
    dotted = client.get("/.well-known/x402.json")
    bare = client.get("/.well-known/x402")
    assert dotted.status_code == 200
    assert dotted.json()["service"] == bare.json()["service"]