"""Unit tests for x402 Facilitator endpoints (/verify, /settle, /supported, /facilitator)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_facilitator_info() -> None:
    """GET /facilitator must return 200 and catalog routes, not 404."""
    response = client.get("/facilitator")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "x402-facilitator"
    assert data["status"] == "ok"
    assert "supported" in data["endpoints"]
    assert "verify" in data["endpoints"]
    assert "settle" in data["endpoints"]


def test_facilitator_supported_routes() -> None:
    """Both /supported and /facilitator/supported must return 200 with kinds array."""
    for path in ("/supported", "/facilitator/supported"):
        response = client.get(path)
        assert response.status_code == 200
        data = response.json()
        assert "kinds" in data
        assert "networks" in data
        assert isinstance(data["kinds"], list)


def test_facilitator_verify_malformed_returns_is_valid_false() -> None:
    """POST /verify and /facilitator/verify on bad body returns 200 with isValid: false."""
    for path in ("/verify", "/facilitator/verify"):
        response = client.post(path, json={"bad": "payload"})
        assert response.status_code == 200
        data = response.json()
        assert data["isValid"] is False
        assert data["is_valid"] is False
        assert "malformed_request" in data["invalidReason"]


def test_facilitator_settle_malformed_returns_success_false() -> None:
    """POST /settle and /facilitator/settle on bad body returns 400 with success: false."""
    for path in ("/settle", "/facilitator/settle"):
        response = client.post(path, json={"bad": "payload"})
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "malformed_request" in data["error"]


@pytest.mark.asyncio
async def test_facilitator_verify_mocked_success() -> None:
    """POST /verify returns isValid: true when server.verify_payment succeeds."""
    mock_server = MagicMock()
    mock_result = MagicMock()
    mock_result.is_valid = True
    mock_result.invalid_reason = None
    mock_server.verify_payment = AsyncMock(return_value=mock_result)

    with patch("app.x402_services._resource_server", return_value=mock_server):
        with patch("app.x402_services._parse_facilitator_input") as mock_parse:
            mock_payload = MagicMock()
            mock_payload.address = "0x1111111111111111111111111111111111111111"
            mock_req = MagicMock()
            mock_req.network = "eip155:8453"
            mock_parse.return_value = (mock_payload, mock_req)

            response = client.post(
                "/verify",
                json={
                    "paymentPayload": {"scheme": "exact"},
                    "paymentRequirements": {"scheme": "exact"},
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["isValid"] is True
            assert data["is_valid"] is True
            assert data["payer"] == "0x1111111111111111111111111111111111111111"


@pytest.mark.asyncio
async def test_facilitator_settle_mocked_success() -> None:
    """POST /settle returns success: true and txHash when settlement succeeds."""
    mock_server = MagicMock()
    mock_verify = MagicMock()
    mock_verify.is_valid = True
    mock_server.verify_payment = AsyncMock(return_value=mock_verify)

    mock_settle = MagicMock()
    mock_settle.model_dump.return_value = {
        "success": True,
        "transaction": "0xabc123789",
        "payer": "0x1111111111111111111111111111111111111111",
        "amount": "0.10",
    }
    mock_server.settle_payment = AsyncMock(return_value=mock_settle)

    with patch("app.x402_services._resource_server", return_value=mock_server):
        with patch("app.x402_services._parse_facilitator_input") as mock_parse:
            mock_payload = MagicMock()
            mock_payload.address = "0x1111111111111111111111111111111111111111"
            mock_req = MagicMock()
            mock_req.network = "eip155:8453"
            mock_req.description = "Test Product"
            mock_parse.return_value = (mock_payload, mock_req)

            response = client.post(
                "/settle",
                json={
                    "paymentPayload": {"scheme": "exact"},
                    "paymentRequirements": {"scheme": "exact"},
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["txHash"] == "0xabc123789"
            assert data["transaction"] == "0xabc123789"
