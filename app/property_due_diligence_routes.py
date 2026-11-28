"""HTTP route for the $0.01 property due diligence agent."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app import demand, property_due_diligence_agent as agent
from app.city_compliance import agentmail, paid_delivery, registry
from app.config import settings

log = logging.getLogger("x402")

router = APIRouter(tags=["agent"])


@router.get("/agent/property-due-diligence")
async def property_due_diligence(
    request: Request,
    city_code: str | None = Query(
        default=None, description="City network code (mn, nyc, sea, …)"
    ),
    address: str | None = Query(
        default=None, description="Street address 1-120 chars"
    ),
) -> JSONResponse:
    """Paid single-address property due diligence agent ($0.01).

    Unpaid always 402 so crawlers index the challenge (even with missing args).
    """
    t0 = time.monotonic()
    if not settings.x402_pay_to_address:
        return JSONResponse(
            status_code=503,
            content={
                "error": "seller_not_configured",
                "detail": "X402_PAY_TO_ADDRESS unset",
            },
        )

    try:
        payment_required = agent.build_payment_required_header()
    except Exception:  # noqa: BLE001
        log.warning("property-due-diligence: cannot build challenge", exc_info=True)
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "30"},
            content={"error": "challenge_unavailable", "detail": "retry shortly"},
        )

    signature = request.headers.get("PAYMENT-SIGNATURE")
    if not signature:
        from app.unpaid_validation import input_hint_agent_query

        if not demand.is_self_traffic(request.headers):
            demand.record_challenge(
                agent.PRODUCT_ID, request.headers.get("user-agent")
            )
        hint = input_hint_agent_query(city_code, address)
        return _402(payment_required, extra=hint)

    code = (city_code or "").strip().lower()
    addr = (address or "").strip()
    if code not in registry.CITIES:
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_city_code",
                "detail": f"expected one of {', '.join(sorted(registry.CITIES))}",
                "known": list(registry.known_codes()),
            },
        )
    if not addr or len(addr) > 120:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_address", "detail": "address must be 1-120 chars"},
        )

    city_mod = registry.get_city(code)
    spec = city_mod.SPEC

    async def _fetch_report(_mod: Any, _address: str) -> dict[str, Any]:
        return await agent.run_check(city_code=code, address=_address)

    class _Runner:
        async def check_property(self, address: str) -> dict[str, Any]:
            return await _fetch_report(city_mod, address)

    runner = _Runner()

    def _notify_error(*, paid: bool, detail: str) -> None:
        agentmail.notify_city_call(
            "error",
            city_code=code,
            city_name=spec.name,
            state=spec.state,
            channel="http",
            address=addr,
            price=agent.PRICE,
            paid=paid,
            detail=detail,
        )

    def _notify_success(*, report: dict, tx: str | None, payer: str | None) -> None:
        latency = round((time.monotonic() - t0) * 1000)
        log.info(
            "property-due-diligence settled",
            extra={"city": code, "status_code": 200, "latency_ms": latency},
        )
        agentmail.notify_city_call(
            "paid_settle",
            city_code=code,
            city_name=spec.name,
            state=spec.state,
            channel="http",
            address=addr,
            price=agent.PRICE,
            verdict=agentmail.verdict_from_report(report),
            paid=True,
            tx_hash=tx,
            payer=payer,
            detail="property-due-diligence agent",
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
            agent_id=agent.PRODUCT_ID,
            amount_usdc=parse_price_usdc(agent.PRICE),
            network=settings.x402_default_network,
            product_id=agent.PRODUCT_ID,
            tx=tx,
            payer=payer,
            request_input=request_input,
            response_body=response_body,
        )

    return await paid_delivery.deliver_paid_city_report(
        signature=signature,
        payment_required=payment_required,
        mod=runner,
        spec=spec,
        address=addr,
        product_id=agent.PRODUCT_ID,
        price=agent.PRICE,
        verify_payment=agent.verify_payment,
        settle_payment=agent.settle_payment,
        notify_error=_notify_error,
        notify_success=_notify_success,
        record_revenue=_record_revenue,
        log_prefix="property-due-diligence",
    )


def _402(payment_required: str, *, extra: dict[str, Any] | None = None) -> JSONResponse:
    content: dict[str, Any] = {
        "error": "payment_required",
        "resource": agent.resource_url(),
        "product_id": agent.PRODUCT_ID,
        "price": agent.PRICE,
        "network": settings.x402_default_network,
        "description": agent.RESOURCE_DESCRIPTION,
        "service_name": agent.SERVICE_NAME,
        "example": agent.DISCOVERY_INPUT_EXAMPLE,
        "how_to_pay": (
            "GET with ?city_code=&address= and PAYMENT-SIGNATURE (x402 v2). "
            "Requirements in PAYMENT-REQUIRED header. Multi-city batch pack: "
            "POST /tasks/us-rental-diligence ($1.50)."
        ),
    }
    if extra:
        content.update(extra)
    return JSONResponse(
        status_code=402,
        headers={"PAYMENT-REQUIRED": payment_required},
        content=content,
    )