"""FastAPI routes for the US City Open-Data Compliance Network."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import demand
from app.city_compliance import agentmail, degraded, gate, paid_delivery, publish, registry
from app.city_compliance.models import CitySpec
from app.config import settings

log = logging.getLogger("x402.city_compliance")

router = APIRouter(tags=["us-city-compliance"])


@router.get("/cities")
async def cities_alias() -> RedirectResponse:
    """Short catalog path — buyers often guess /cities instead of /us/cities."""
    return RedirectResponse(url="/us/cities", status_code=307)


@router.get("/us/cities")
async def us_cities_catalog() -> JSONResponse:
    """Free catalog of network cities (no payment)."""
    cities = registry.list_cities()
    agentmail.notify_city_call(
        "catalog",
        channel="http",
        price=settings.city_network_price,
        detail=f"city_count={len(cities)}",
    )
    return JSONResponse(
        content={
            "network": "us-city-open-data-compliance",
            "price": settings.city_network_price,
            "network_caip2": settings.x402_default_network,
            "cities": cities,
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
        raw = await mod.check_property(spec.sample_address)
        report = publish.prepare_city_report(
            raw, spec=spec, address_fallback=spec.sample_address
        )
    except Exception:
        log.warning("us/%s sample upstream failed", spec.code, exc_info=True)
        agentmail.notify_city_call(
            "error",
            city_code=spec.code,
            city_name=spec.name,
            state=spec.state,
            channel="http",
            address=spec.sample_address,
            detail="upstream_open_data_unavailable",
        )
        report = publish.prepare_city_report(
            degraded.upstream_unavailable_report(spec, spec.sample_address),
            spec=spec,
            address_fallback=spec.sample_address,
        )
    agentmail.notify_city_call(
        "sample",
        city_code=spec.code,
        city_name=spec.name,
        state=spec.state,
        channel="http",
        address=spec.sample_address,
        price=gate.price_for(spec),
        verdict=agentmail.verdict_from_report(report),
        paid=False,
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
    output_example = publish.discovery_output_example(mod)
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
        from app.unpaid_validation import input_hint_city_address

        content: dict[str, object] = {
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
        }
        hint = input_hint_city_address(address, spec.code)
        if hint:
            content.update(hint)
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
            content=content,
        )

    if address is None or not address.strip() or len(address) > 120:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_address", "detail": "address must be 1-120 chars"},
        )

    addr = address.strip()

    def _notify_error(*, paid: bool, detail: str) -> None:
        agentmail.notify_city_call(
            "error",
            city_code=spec.code,
            city_name=spec.name,
            state=spec.state,
            channel="http",
            address=addr,
            price=gate.price_for(spec),
            paid=paid,
            detail=detail,
        )

    def _notify_success(*, report: dict, tx: str | None, payer: str | None) -> None:
        latency = round((time.monotonic() - t0) * 1000)
        log.info(
            "us/%s/property-check settled",
            spec.code,
            extra={"address": address, "status_code": 200, "latency_ms": latency},
        )
        agentmail.notify_city_call(
            "paid_settle",
            city_code=spec.code,
            city_name=spec.name,
            state=spec.state,
            channel="http",
            address=addr,
            price=gate.price_for(spec),
            verdict=agentmail.verdict_from_report(report),
            paid=True,
            tx_hash=tx,
            payer=payer,
        )

    def _record_revenue(
        *,
        tx: str | None,
        payer: object,
        request_input: object | None = None,
        response_body: object | None = None,
    ) -> None:
        from app.swarm import ledger_writer
        from app.swarm.publisher import parse_price_usdc

        ledger_writer.record_revenue(
            agent_id=pid,
            amount_usdc=parse_price_usdc(gate.price_for(spec)),
            network=settings.x402_default_network,
            product_id=pid,
            tx=tx,
            payer=payer,
            request_input=request_input,
            response_body=response_body,
        )

    return await paid_delivery.deliver_paid_city_report(
        signature=signature,
        payment_required=payment_required,
        mod=mod,
        spec=spec,
        address=addr,
        product_id=pid,
        price=gate.price_for(spec),
        verify_payment=gate.verify_payment,
        settle_payment=gate.settle_payment,
        notify_error=_notify_error,
        notify_success=_notify_success,
        record_revenue=_record_revenue,
        log_prefix=f"us/{spec.code}/property-check",
    )


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
