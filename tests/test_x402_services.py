"""x402 service unit tests (no wallet required)."""

import pytest

from app.models import DiscoverServicesInput, GetPaymentRequirementsInput
from app import x402_services


def test_supported_networks() -> None:
    result = x402_services.get_supported_networks()
    assert result.protocol_version == "v2"
    assert any(n["id"] == "eip155:8453" for n in result.networks)
    assert "PAYMENT-SIGNATURE" in result.headers


@pytest.mark.asyncio
async def test_get_payment_requirements_public_url() -> None:
    """Probe a public URL — may or may not return 402."""
    params = GetPaymentRequirementsInput(url="https://httpbin.org/status/402")
    result = await x402_services.get_payment_requirements(params)
    assert "status_code" in result
    assert result["status_code"] in (402, 200, 503)


@pytest.mark.asyncio
async def test_discover_services_structure() -> None:
    params = DiscoverServicesInput(limit=5)
    try:
        result = await x402_services.discover_services(params)
    except Exception as exc:
        pytest.skip(f"Discovery API unavailable: {exc}")

    assert "services" in result
    assert "count" in result
    assert isinstance(result["services"], list)


@pytest.mark.asyncio
async def test_pay_and_fetch_requires_wallet() -> None:
    from app.models import PayAndFetchInput

    params = PayAndFetchInput(url="https://example.com/paid")
    with pytest.raises(ValueError, match="EVM_PRIVATE_KEY"):
        await x402_services.pay_and_fetch(params)