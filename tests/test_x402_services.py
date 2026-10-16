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
async def test_get_payment_requirements_public_url(probe_402_url: str) -> None:
    """Probe a 402-returning URL (local fixture — no httpbin.org flakiness)."""
    params = GetPaymentRequirementsInput(url=probe_402_url)
    result = await x402_services.get_payment_requirements(params)
    assert "status_code" in result
    assert result["status_code"] == 402


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
    assert result["count"] == len(result["services"])
    assert "partial_results" in result


@pytest.mark.asyncio
async def test_discover_services_search_query_uses_cdp_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: server-side search must not empty-filter a non-empty CDP page."""
    from app.config import settings

    captured: dict[str, object] = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "partialResults": False,
                "resources": [
                    {
                        "description": "Weather forecast",
                        "accepts": [{"amount": "2000", "network": "eip155:8453"}],
                    }
                ],
                "searchMethod": "keyword",
            }

    async def fake_get(self, url: str, params=None, **kwargs):  # noqa: ANN001
        captured["url"] = url
        captured["params"] = dict(params or {})
        return _FakeResponse()

    monkeypatch.setattr(settings, "cdp_discovery_search_url", "https://discovery.test/search")
    monkeypatch.setattr(
        x402_services,
        "_facilitator_client",
        lambda network=None: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    params = DiscoverServicesInput(query="weather", limit=5)
    result = await x402_services.discover_services(params)

    assert captured["url"] == "https://discovery.test/search"
    assert captured["params"]["query"] == "weather"
    assert captured["params"]["limit"] == 5
    assert result["count"] == 1
    assert result["services"][0]["description"] == "Weather forecast"
    assert result["facilitator_supported"] is None


@pytest.mark.asyncio
async def test_discover_services_does_not_filter_by_seller_pay_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Buyer catalog search must not scope to this storefront's cashier payTo."""
    from app.config import settings

    captured: dict[str, object] = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"partialResults": False, "resources": []}

    async def fake_get(self, url: str, params=None, **kwargs):  # noqa: ANN001
        captured["params"] = dict(params or {})
        return _FakeResponse()

    monkeypatch.setattr(
        settings,
        "x402_pay_to_address",
        "0x05e1720bB82F86B5bc7940a99FDC702E32256357",
    )
    monkeypatch.setattr(settings, "cdp_discovery_search_url", "https://discovery.test/search")
    monkeypatch.setattr(
        x402_services,
        "_facilitator_client",
        lambda network=None: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    await x402_services.discover_services(DiscoverServicesInput(query="weather", limit=5))

    params = captured["params"]
    assert "payTo" not in params


def test_effective_mn_data_base_url_rejects_stale_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import mn_compliance
    from app.config import settings

    monkeypatch.setattr(
        settings,
        "mn_data_base_url",
        "https://services.arcgis.com/afSMGVsArcGISTools/ArcGIS/rest/services",
    )
    assert (
        mn_compliance.effective_mn_data_base_url()
        == mn_compliance.CANONICAL_MN_DATA_BASE_URL
    )


@pytest.mark.asyncio
async def test_pay_and_fetch_requires_wallet(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings
    from app.models import PayAndFetchInput

    monkeypatch.setattr(settings, "evm_private_key", None)
    params = PayAndFetchInput(url="https://example.com/paid")
    with pytest.raises(ValueError, match="EVM_PRIVATE_KEY"):
        await x402_services.pay_and_fetch(params)


@pytest.mark.asyncio
async def test_malformed_signature_returns_invalid_not_raise() -> None:
    """Garbage PAYMENT-SIGNATURE must 402, not 500 — live Render 500'd on this."""
    from app.models import VerifyPaymentInput

    result = await x402_services._verify_and_settle_payment(
        VerifyPaymentInput(payment_signature="e30=", payment_required="e30=")
    )
    assert result["is_valid"] is False
    assert result["payment_settled"] is False
    assert result["invalid_reason"]
    assert result["invalid_reason"].startswith("malformed_payment")


def test_parse_caip2_networks_splits_and_strips() -> None:
    assert x402_services.parse_caip2_networks(None) == []
    assert x402_services.parse_caip2_networks("") == []
    assert x402_services.parse_caip2_networks("eip155:8453") == ["eip155:8453"]
    assert x402_services.parse_caip2_networks(
        "eip155:8453, solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp,eip155:42161"
    ) == [
        "eip155:8453",
        "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
        "eip155:42161",
    ]
    assert (
        x402_services.primary_caip2_network(
            "eip155:8453,solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
        )
        == "eip155:8453"
    )


def test_buyer_cap_rounds_list_price_to_10000_atomic() -> None:
    """int(0.01 * 1e6) truncates to 9999 on some platforms and refuses $0.01."""
    assert x402_services.usdc_cap_atomic(0.01) == 10_000
    assert x402_services.usdc_cap_atomic(0.02) == 20_000


@pytest.mark.asyncio
async def test_pay_and_fetch_price_cap_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_price_usdc must surface as a clear refusal, not a raw SDK error."""
    from x402 import NoMatchingRequirementsError
    from x402.http.clients import x402HttpxClient

    from app.config import settings
    from app.models import PayAndFetchInput

    monkeypatch.setattr(settings, "evm_private_key", "0x" + "11" * 32)

    async def refuse(self, *args, **kwargs):
        raise NoMatchingRequirementsError("all options exceed cap")

    monkeypatch.setattr(x402HttpxClient, "request", refuse)

    params = PayAndFetchInput(url="https://example.com/paid", max_price_usdc=0.0001)
    with pytest.raises(ValueError, match="payment refused"):
        await x402_services.pay_and_fetch(params)
