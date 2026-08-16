"""FastAPI routes for the US City Open-Data Compliance Network."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app import demand
from app.city_compliance import gate, registry
from app.city_compliance.models import CitySpec
from app.config import settings

log = logging.getLogger("x402.city_compliance")

router = APIRouter(tags=["us-city-compliance"])


@router.get("/us/cities")
async def us_cities_catalog() -> JSONResponse:
    """Free catalog of network cities (no payment)."""
    return JSONResponse(
        content={
            "network": "us-city-open-data-compliance",
            "price": settings.city_network_price,
            "network_caip2": settings.x402_default_network,
            "cities": registry.list_cities(),
            "note": (
                "Each city is a separate paid resource at "
                "/us/{code}/property-check. Minneapolis (mn) is also available "
                "at the canonical /mn/property-check path."
            ),
        }
    )


@router.get("/us/{city_code}/property-check/sample")
async def us_city_sample(city_code: str) -> JSONResponse:
    """Free fixed-address sample for one city."""
    try:
        mod = registry.get_city(city_code)
    except KeyError:
        return _unknown_city(city_code)

    spec: CitySpec = mod.SPEC
    try:
        report = await mod.check_property(spec.sample_address)
    except Exception:
        log.warning("us/%s sample upstream failed", spec.code, exc_info=True)
        return JSONResponse(
            status_code=502,
            content={
                "error": "upstream_open_data_unavailable",
                "city": spec.code,
                "detail": "city open-data source timed out or refused; retry shortly",
            },
        )
    return JSONResponse(
        content={
            "sample": True,
            "city": spec.code,
            "sample_address": spec.sample_address,
            "note": spec.sample_note,
            "paid_endpoint": gate.resource_url(spec),
            "price": gate.price_for(spec),
            "report": report,
            "next": {
                "paid_url": gate.resource_url(spec),
                "mcp_tool": "check_us_city_property",
                "mcp_args": {
                    "city_code": spec.code,
                    "address": "<street address 1-120 chars>",
                },
                "http": f"{gate.resource_url(spec)}?address=<url-encoded street>",
            },
        }
    )


@router.get("/us/{city_code}/property-check")
async def us_city_property_check(
    city_code: str,
    request: Request,
    address: str | None = Query(
        default=None, description="Street address in the target city, 1-120 chars"
    ),
) -> JSONResponse:
    """Paid x402 resource: city open-data compliance snapshot.

    Unpaid always returns 402 (even with missing address) so discovery crawlers
    index the challenge. Address is validated only on the paid path.
    """
    try:
        mod = registry.get_city(city_code)
    except KeyError:
        return _unknown_city(city_code)

    spec: CitySpec = mod.SPEC
    t0 = time.monotonic()
    if not settings.x402_pay_to_address:
        return JSONResponse(
            status_code=503,
            content={"error": "seller_not_configured", "detail": "X402_PAY_TO_ADDRESS unset"},
        )

    input_example = {"address": spec.sample_address}
    output_example = mod.discovery_output_example()
    try:
        payment_required = gate.build_payment_required_header(
            spec, input_example=input_example, output_example=output_example
        )
    except Exception:
        log.warning("us/%s/property-check: cannot build challenge", spec.code, exc_info=True)
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "30"},
            content={"error": "challenge_unavailable", "detail": "retry shortly"},
        )

    signature = request.headers.get("PAYMENT-SIGNATURE")
    pid = gate.product_id(spec)
    if not signature:
        log.info(
            "us/%s/property-check 402 (no signature)",
            spec.code,
            extra={"address": address, "status_code": 402},
        )
        if not demand.is_self_traffic(request.headers):
            demand.record_challenge(pid, request.headers.get("user-agent"))
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_required},
            content={
                "error": "payment_required",
                "resource": gate.resource_url(spec),
                "price": gate.price_for(spec),
                "network": settings.x402_default_network,
                "city": spec.code,
                "description": spec.description,
                "sample_url": gate.sample_url(spec),
                "catalog_url": f"{settings.public_base_url.rstrip('/')}/us/cities",
                "how_to_pay": (
                    "Retry with PAYMENT-SIGNATURE header (x402 v2); requirements "
                    "are in the PAYMENT-REQUIRED response header. Free fixed-address "
                    f"sample (no payment): GET {gate.sample_url(spec)}. "
                    "MCP golden path: list_us_cities → get_us_city_property_sample → "
                    "check_us_city_property (or pay_and_fetch on this resource URL)."
                ),
            },
        )

    if address is None or not address.strip() or len(address) > 120:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_address", "detail": "address must be 1-120 chars"},
        )

    result = await gate.verify_and_settle(signature, payment_required)
    if not result["is_valid"] or not result["payment_settled"]:
        log.warning(
            "us/%s/property-check payment invalid",
            spec.code,
            extra={"address": address, "status_code": 402},
        )
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_required},
            content={
                "error": "payment_invalid",
                "invalid_reason": result.get("invalid_reason"),
                "settlement_error": result.get("settlement_error"),
            },
        )

    try:
        report = await mod.check_property(address)
    except Exception:
        log.warning("us/%s property join failed after settle", spec.code, exc_info=True)
        # Payment already settled — never re-challenge; return 502 with receipt.
        settlement = result.get("settlement") or {}
        receipt = base64.b64encode(json.dumps(settlement).encode()).decode()
        return JSONResponse(
            status_code=502,
            headers={"PAYMENT-RESPONSE": receipt},
            content={
                "error": "upstream_open_data_unavailable",
                "city": spec.code,
                "detail": "payment settled; city open-data join failed; contact seller",
            },
        )
    latency = round((time.monotonic() - t0) * 1000)
    log.info(
        "us/%s/property-check settled",
        spec.code,
        extra={"address": address, "status_code": 200, "latency_ms": latency},
    )

    settlement = result.get("settlement") or {}
    tx = settlement.get("transaction") or settlement.get("txHash")
    try:
        from app.swarm import ledger_writer
        from app.swarm.publisher import parse_price_usdc

        ledger_writer.record_revenue(
            agent_id=pid,
            amount_usdc=parse_price_usdc(gate.price_for(spec)),
            network=settings.x402_default_network,
            product_id=pid,
            tx=str(tx) if tx else None,
            payer=settlement.get("payer"),
        )
    except Exception:
        log.warning("us/%s revenue ledger write failed", spec.code, exc_info=True)

    receipt = base64.b64encode(json.dumps(result["settlement"]).encode()).decode()
    return JSONResponse(content=report, headers={"PAYMENT-RESPONSE": receipt})


def _unknown_city(city_code: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": "unknown_city",
            "city": city_code,
            "known": list(registry.known_codes()),
            "catalog": "/us/cities",
        },
    )
