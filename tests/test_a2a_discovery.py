"""Tests for active A2A agent card discovery and resolution."""
from __future__ import annotations

import pytest

from app.a2a_discovery import (
    A2A_X402_URI,
    AP2_URI,
    normalize_target_urls,
    parse_agent_card,
    resolve_agent_card,
)
from app.ssrf_guard import validate_probe_url


def test_ssrf_blocking_on_a2a_targets() -> None:
    with pytest.raises(ValueError):
        validate_probe_url("http://127.0.0.1/.well-known/agent-card.json")

    with pytest.raises(ValueError):
        validate_probe_url("http://localhost:8000/agent.json")

    with pytest.raises(ValueError):
        validate_probe_url("http://169.254.169.254/metadata")


def test_normalize_target_urls() -> None:
    urls = normalize_target_urls("example.com")
    assert "https://example.com/.well-known/agent-card.json" in urls
    assert "https://example.com/.well-known/agent.json" in urls

    direct = normalize_target_urls("https://example.com/custom-card.json")
    assert direct == ["https://example.com/custom-card.json"]


def test_parse_agent_card_with_extensions() -> None:
    mock_card = {
        "protocolVersion": "1.0",
        "name": "Partner Agent",
        "capabilities": {
            "extensions": [
                {"uri": A2A_X402_URI},
                {"uri": AP2_URI},
            ]
        },
        "payments": {
            "rails": [
                {
                    "network": "eip155:8453",
                    "asset": "USDC",
                    "payTo": "0x1111111111111111111111111111111111111111",
                }
            ]
        },
        "skills": [
            {
                "id": "risk-scoring",
                "name": "Risk Scoring",
                "price_usdc": "0.10",
                "network": "eip155:8453",
            }
        ],
    }

    parsed = parse_agent_card(mock_card, "https://example.com/.well-known/agent-card.json")
    assert parsed["status"] == "valid"
    assert parsed["has_x402_extension"] is True
    assert parsed["has_ap2_extension"] is True
    assert parsed["pay_to"] == "0x1111111111111111111111111111111111111111"
    assert parsed["skills_count"] == 1
    assert parsed["skills"][0]["price_usdc"] == "0.10"


@pytest.mark.asyncio
async def test_resolve_agent_card_ssrf_blocked_fails_closed() -> None:
    result = await resolve_agent_card("http://127.0.0.1:8000/agent.json")
    assert result["status"] == "unresolved"
    assert "SSRF" in result["error"] or "blocked" in result["error"].lower()


def test_a2a_resolve_http_endpoint_ssrf_blocked() -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/a2a/resolve", params={"url": "http://127.0.0.1:8000/agent.json"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unresolved"
    assert "SSRF" in data["error"] or "blocked" in data["error"].lower()
