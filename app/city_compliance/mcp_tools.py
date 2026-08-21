"""MCP-facing wrappers around the US City Open-Data Compliance Network.

Thin packaging only — no new product surface. Catalog + free samples hit the
in-process registry; paid checks route through the same HTTP x402 URLs external
buyers use (``pay_and_fetch`` / ``get_payment_requirements``).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.city_compliance import gate, registry
from app.config import settings
from app.models import GetPaymentRequirementsInput, PayAndFetchInput
from app import x402_services


def _catalog_payload() -> dict[str, Any]:
    base = settings.public_base_url.rstrip("/")
    cities = registry.list_cities()
    return {
        "network": "us-city-open-data-compliance",
        "price": settings.city_network_price,
        "network_caip2": settings.x402_default_network,
        "city_count": len(cities),
        "cities": cities,
        "catalog_url": f"{base}/us/cities",
        "golden_path": {
            "1_catalog": "list_us_cities (this tool) or GET /us/cities",
            "2_sample": (
                "get_us_city_property_sample(city_code=…) — free fixed-address "
                "shape check before paying"
            ),
            "3_paid": (
                "check_us_city_property(city_code=…, address=…) — requires "
                "EVM_PRIVATE_KEY on the MCP client host; settles USDC via x402"
            ),
            "http_equivalent": (
                f"GET {base}/us/{{code}}/property-check?address=… "
                "with PAYMENT-SIGNATURE after 402"
            ),
        },
        "note": (
            "Each city is a separate paid resource at /us/{code}/property-check. "
            "Minneapolis (mn) is also available at canonical /mn/property-check."
        ),
    }


async def list_us_cities() -> dict[str, Any]:
    """Free machine catalog — same payload shape as GET /us/cities + MCP path."""
    return _catalog_payload()


async def get_us_city_property_sample(city_code: str) -> dict[str, Any]:
    """Free fixed-address sample for one city (no payment)."""
    code = (city_code or "").strip().lower()
    try:
        mod = registry.get_city(code)
    except KeyError:
        return {
            "error": "unknown_city",
            "city": city_code,
            "known": list(registry.known_codes()),
            "catalog_url": f"{settings.public_base_url.rstrip('/')}/us/cities",
            "hint": "Call list_us_cities() for codes, paid_url, and sample_address.",
        }

    spec = mod.SPEC
    try:
        report = await mod.check_property(spec.sample_address)
    except Exception as exc:  # noqa: BLE001 — surface upstream failure to agent
        return {
            "error": "upstream_open_data_unavailable",
            "city": spec.code,
            "detail": "city open-data source timed out or refused; retry shortly",
            "exception_type": type(exc).__name__,
            "sample_url": gate.sample_url(spec),
            "paid_url": gate.resource_url(spec),
        }

    paid = gate.resource_url(spec)
    return {
        "sample": True,
        "city": spec.code,
        "name": spec.name,
        "state": spec.state,
        "sample_address": spec.sample_address,
        "note": spec.sample_note,
        "paid_endpoint": paid,
        "paid_url": paid,
        "sample_url": gate.sample_url(spec),
        "price": gate.price_for(spec),
        "network": settings.x402_default_network,
        "report": report,
        "next": {
            "action": "check_us_city_property",
            "city_code": spec.code,
            "address": "<street address 1-120 chars>",
            "requires_env": ["EVM_PRIVATE_KEY"],
            "http": f"{paid}?address=<url-encoded street>",
            "note": (
                "Sample is a fixed address only. Pay for an arbitrary address "
                "via check_us_city_property or pay_and_fetch on paid_url."
            ),
        },
    }


def _paid_url(city_code: str, address: str) -> tuple[Any, str] | dict[str, Any]:
    code = (city_code or "").strip().lower()
    try:
        mod = registry.get_city(code)
    except KeyError:
        return {
            "error": "unknown_city",
            "city": city_code,
            "known": list(registry.known_codes()),
            "catalog_url": f"{settings.public_base_url.rstrip('/')}/us/cities",
        }
    addr = (address or "").strip()
    if not addr or len(addr) > 120:
        return {
            "error": "invalid_address",
            "detail": "address must be 1-120 chars",
            "city": code,
            "sample_address": mod.SPEC.sample_address,
            "hint": (
                f"Try get_us_city_property_sample(city_code={code!r}) for a free "
                "fixed-address report first."
            ),
        }
    url = f"{gate.resource_url(mod.SPEC)}?address={quote(addr, safe='')}"
    return mod, url


async def check_us_city_property(
    city_code: str,
    address: str,
    *,
    max_price_usdc: float | None = None,
    preferred_network: str | None = None,
) -> dict[str, Any]:
    """Paid compliance check via the live HTTP x402 resource.

    With ``EVM_PRIVATE_KEY`` set, settles and returns the report body.
    Without a buyer key, probes the 402 challenge and returns a handoff package
    (no settlement) so agents still get a complete discovery → pay path.
    """
    resolved = _paid_url(city_code, address)
    if isinstance(resolved, dict):
        return resolved
    mod, url = resolved
    spec = mod.SPEC
    price = gate.price_for(spec)
    sample = gate.sample_url(spec)

    if not settings.evm_private_key:
        probe = await x402_services.get_payment_requirements(
            GetPaymentRequirementsInput(url=url, method="GET")
        )
        return {
            "paid": False,
            "reason": "buyer_wallet_not_configured",
            "city": spec.code,
            "address": address.strip(),
            "paid_url": url,
            "sample_url": sample,
            "price": price,
            "network": settings.x402_default_network,
            "payment_probe": probe,
            "how_to_pay": (
                "Set EVM_PRIVATE_KEY on the MCP client host, then re-call "
                "check_us_city_property (or pay_and_fetch on paid_url). "
                f"Free shape check first: get_us_city_property_sample("
                f"city_code={spec.code!r})."
            ),
            "mcp": {
                "tool": "check_us_city_property",
                "requires_env": ["EVM_PRIVATE_KEY"],
                "alternate_tool": "pay_and_fetch",
                "alternate_args": {"url": url, "method": "GET"},
            },
        }

    result = await x402_services.pay_and_fetch(
        PayAndFetchInput(
            url=url,
            method="GET",
            preferred_network=preferred_network or settings.x402_default_network,
            max_price_usdc=max_price_usdc,
        )
    )
    return {
        "paid": True,
        "city": spec.code,
        "address": address.strip(),
        "paid_url": url,
        "price": price,
        "network": settings.x402_default_network,
        "result": result,
    }
