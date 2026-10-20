"""x402 MCP seller payment wrappers (FastMCP + create_payment_wrapper)."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.agent_surface import DEFAULT_PAY_TO
from app.config import settings
from app.city_compliance import gate, registry
from app import x402_services

log = logging.getLogger(__name__)

MCP_STREAMABLE_HTTP_PATH = "/mcp/mcp"


def mcp_resource_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}{MCP_STREAMABLE_HTTP_PATH}"


@lru_cache(maxsize=1)
def get_mcp_resource_server() -> Any:
    """Shared x402ResourceServer with Bazaar extension for MCP tool settlement."""
    from x402.extensions.bazaar import bazaar_resource_server_extension

    server = x402_services._resource_server(settings.x402_default_network)
    try:
        server.register_extension(bazaar_resource_server_extension)
    except Exception:  # noqa: BLE001 — extension may already be registered
        pass
    return server


def _city_check_description() -> str:
    return (
        "Paid US city property compliance check (MCP seller). "
        f"Price: {settings.city_network_price} per call (x402, USDC on Base). "
        "Use city.sample first for a free fixed-address shape check."
    )


def _city_check_bazaar_extensions() -> dict[str, Any]:
    from x402.extensions.bazaar import (
        DeclareMcpDiscoveryConfig,
        OutputConfig,
        declare_mcp_discovery_extension,
    )

    mn = registry.get_city("mn")
    output_example = mn.discovery_output_example()
    return declare_mcp_discovery_extension(
        DeclareMcpDiscoveryConfig(
            tool_name="city.check",
            description=_city_check_description(),
            transport="streamable-http",
            input_schema={
                "type": "object",
                "properties": {
                    "city_code": {
                        "type": "string",
                        "description": "City code from city.list (e.g. mn, sea, nyc).",
                    },
                    "address": {
                        "type": "string",
                        "description": "Street address in the target city, 1-120 chars.",
                    },
                },
                "required": ["city_code", "address"],
            },
            example={"city_code": "mn", "address": "1700 Penn Ave N"},
            output=OutputConfig(example=output_example),
        )
    )


def build_city_check_payment_bundle() -> tuple[list[Any], Any, dict[str, Any]]:
    """PaymentRequirements, ResourceInfo, and Bazaar extensions for city.check."""
    from x402 import ResourceConfig
    from x402.schemas import ResourceInfo

    pay_to = settings.x402_pay_to_address or DEFAULT_PAY_TO
    if not pay_to:
        raise ValueError("X402_PAY_TO_ADDRESS required for MCP paid tools")

    network = settings.x402_default_network
    price = settings.city_network_price
    description = x402_services._clamp_description(_city_check_description())

    server = get_mcp_resource_server()
    config = ResourceConfig(
        scheme="exact",
        network=network,
        pay_to=pay_to,
        price=price,
        description=description,
    )
    accepts = list(server.build_payment_requirements(config))
    if not accepts:
        raise ValueError("could not build payment requirements for city.check")

    resource = ResourceInfo(
        url=mcp_resource_url(),
        description=description,
        mime_type="application/json",
        service_name=(settings.bazaar_service_name or "US City Compliance")[:32],
        tags=x402_services._normalize_service_tags(None) or None,
    )
    extensions = _city_check_bazaar_extensions()
    return accepts, resource, extensions


def _record_city_check_settlement(ctx: Any) -> None:
    """Mirror HTTP city property-check revenue into the ledger after MCP settle."""
    try:
        result = getattr(ctx, "settlement", None)
        if getattr(result, "success", None) is not True:
            return

        city_code = str(ctx.arguments.get("city_code") or "").strip().lower()
        if not city_code:
            return
        try:
            mod = registry.get_city(city_code)
        except KeyError:
            return

        spec = mod.SPEC
        product_id = gate.product_id(spec)
        requirements = getattr(ctx, "payment_requirements", None)
        amount = x402_services.atomic_to_units(
            getattr(result, "amount", None),
            getattr(result, "network", None) or getattr(requirements, "network", None),
            getattr(requirements, "asset", None),
        )
        if amount is None:
            from app.swarm.publisher import parse_price_usdc

            amount = parse_price_usdc(gate.price_for(spec))

        tx = getattr(result, "transaction", None) or ""
        payer = getattr(result, "payer", None)

        from app.swarm import ledger_writer

        ledger_writer.record_revenue(
            agent_id=product_id,
            amount_usdc=amount,
            network=str(
                getattr(result, "network", None)
                or getattr(requirements, "network", None)
                or settings.x402_default_network
            ),
            product_id=product_id,
            tx=str(tx) if tx else None,
            payer=str(payer) if payer else None,
        )
    except Exception:
        log.warning("city.check MCP settlement ledger write failed", exc_info=True)


@lru_cache(maxsize=1)
def city_check_payment_wrapper() -> Any:
    from x402.mcp import create_payment_wrapper
    from x402.mcp.types import PaymentWrapperHooks

    accepts, resource, extensions = build_city_check_payment_bundle()
    hooks = PaymentWrapperHooks(on_after_settlement=_record_city_check_settlement)
    return create_payment_wrapper(
        get_mcp_resource_server(),
        accepts=accepts,
        resource=resource,
        extensions=extensions,
        hooks=hooks,
    )
