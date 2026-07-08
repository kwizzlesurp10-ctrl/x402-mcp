"""Positive pay-and-fetch flow via mocked x402HttpxClient transport."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import PayAndFetchInput
from app import x402_services


@pytest.mark.asyncio
async def test_pay_and_fetch_success_without_settlement_header(monkeypatch) -> None:
    """200 without PAYMENT-RESPONSE must not crash; settlement optional."""
    monkeypatch.setattr(
        x402_services.settings,
        "evm_private_key",
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    )

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.status_code = 200
    mock_response.text = '{"paid":"resource"}'
    mock_response.headers = {}
    mock_response.aread = AsyncMock()

    mock_http = AsyncMock()
    mock_http.request = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)

    with patch("x402.http.clients.x402HttpxClient", return_value=mock_http):
        result = await x402_services.pay_and_fetch(
            PayAndFetchInput(url="https://example.com/paid-resource")
        )

    assert result["status_code"] == 200
    assert "paid" in result["body"]
    assert result["payment_settled"] is False
    assert result["settlement_parse_error"] is not None


@pytest.mark.asyncio
async def test_pay_and_fetch_with_settlement_header(monkeypatch) -> None:
    """Full buyer flow: 200 + PAYMENT-RESPONSE parsed via SDK."""
    monkeypatch.setattr(
        x402_services.settings,
        "evm_private_key",
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    )

    settle_payload = {
        "success": True,
        "transaction": "0xabc123",
        "network": "eip155:84532",
    }
    from x402.schemas import SettleResponse

    settle = SettleResponse.model_validate(
        {
            "success": True,
            "transaction": "0xabc123",
            "network": "eip155:84532",
        }
    )
    from x402.http.utils import encode_payment_response_header

    header_val = encode_payment_response_header(settle)

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.status_code = 200
    mock_response.text = '{"result":"ok"}'
    mock_response.headers = {"PAYMENT-RESPONSE": header_val}
    mock_response.aread = AsyncMock()

    mock_http = AsyncMock()
    mock_http.request = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)

    with patch("x402.http.clients.x402HttpxClient", return_value=mock_http):
        result = await x402_services.pay_and_fetch(
            PayAndFetchInput(url="https://example.com/paid-resource")
        )

    assert result["status_code"] == 200
    assert result["payment_settled"] is True
    assert result["payment_settlement"] is not None
    assert result["settlement_parse_error"] is None