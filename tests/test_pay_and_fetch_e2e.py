"""Positive pay-and-fetch flow via mocked x402HttpxClient transport."""

import base64
import json
from types import SimpleNamespace
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

# ---------------------------------------------------------------------------
# What was actually CHARGED. max_price_usdc is a ceiling, not a price, and a
# caller that ledgers the ceiling overstates its own spend.
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402


def test_atomic_amounts_convert_at_the_assets_own_decimals() -> None:
    usdc = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base mainnet USDC, 6dp
    assert x402_services.asset_decimals("eip155:8453", usdc) == 6
    assert x402_services.atomic_to_units("10000", "eip155:8453", usdc) == 0.01
    assert x402_services.atomic_to_units("1000") == 0.001
    # Unknown asset / network: fall back to USDC's 6 rather than raising.
    assert x402_services.asset_decimals("eip155:8453", "0xnope") == 6
    assert x402_services.asset_decimals(None, None) == 6


@pytest.mark.parametrize("bad", [None, "", "abc", "1.5", "-1", True, False, {}])
def test_an_unusable_atomic_amount_is_absent_not_guessed(bad) -> None:
    """A wrong number in a money ledger is worse than a missing one."""
    assert x402_services.atomic_to_units(bad) is None


def test_the_facilitators_settled_amount_wins() -> None:
    amount, source = x402_services.charged_amount(
        {"amount": "4000", "network": "eip155:8453"},
        {"amount_atomic": "10000", "network": "eip155:8453"},
    )
    assert (amount, source) == (0.004, "settlement")


def test_the_signed_requirement_is_the_fallback() -> None:
    """CDP does not always echo an amount; what the buyer signed for is still
    exact, and still not the cap."""
    amount, source = x402_services.charged_amount(
        {"amount": None, "network": "eip155:8453"},
        {"amount_atomic": "1000", "network": "eip155:8453"},
    )
    assert (amount, source) == (0.001, "authorized")


def test_nothing_is_invented_when_neither_side_has_an_amount() -> None:
    assert x402_services.charged_amount(None, None) == (None, None)
    assert x402_services.charged_amount({}, {}) == (None, None)


def test_the_signed_requirements_capture_reads_the_selected_option() -> None:
    """Pins the shape of x402 2.14.0's PaymentCreatedContext."""
    store, capture = x402_services.signed_requirements_capture()
    capture(
        SimpleNamespace(
            selected_requirements=SimpleNamespace(
                amount="1000", asset="0xUSDC", network="eip155:8453"
            )
        )
    )
    assert store == {
        "amount_atomic": "1000",
        "asset": "0xUSDC",
        "network": "eip155:8453",
    }


def test_the_capture_hook_never_raises_into_payment_creation() -> None:
    store, capture = x402_services.signed_requirements_capture()
    capture(SimpleNamespace(selected_requirements=None))
    capture(object())
    capture(None)
    assert store == {}


@pytest.mark.asyncio
async def test_a_settled_response_reports_the_charge(monkeypatch) -> None:
    monkeypatch.setattr(
        x402_services.settings,
        "evm_private_key",
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    )
    from x402.http.utils import encode_payment_response_header
    from x402.schemas import SettleResponse

    header_val = encode_payment_response_header(
        SettleResponse.model_validate(
            {
                "success": True,
                "transaction": "0xabc123",
                "network": "eip155:8453",
                "amount": "1000",
            }
        )
    )

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
            PayAndFetchInput(
                url="https://example.com/paid-resource", max_price_usdc=0.05
            )
        )

    assert result["payment_settled"] is True
    # The cap was $0.05; the charge was $0.001.
    assert result["amount_charged_usdc"] == 0.001
    assert result["amount_charged_source"] == "settlement"


@pytest.mark.asyncio
async def test_an_unsettled_response_reports_no_charge(monkeypatch) -> None:
    """No funds moved, so there is no charge to report — not even the cap."""
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
            PayAndFetchInput(
                url="https://example.com/paid-resource", max_price_usdc=0.05
            )
        )

    assert result["payment_settled"] is False
    assert result["amount_charged_usdc"] is None
    assert result["amount_charged_source"] is None
