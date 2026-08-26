"""HTTP route for the $0.01 property due diligence agent."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app import demand, property_due_diligence_agent as agent
from app.city_compliance import registry
from app.config import settings
from app.swarm.publisher import parse_price_usdc

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
        if not demand.is_self_traffic(request.headers):
            demand.record_challenge(
                agent.PRODUCT_ID, request.headers.get("user-agent")
            )
        return _402(payment_required)

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

    result = await agent.verify_and_settle(signature, payment_required)
    if not result.get("is_valid") or not result.get("payment_settled"):
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_required},
            content={
                "error": "payment_invalid",
                "invalid_reason": result.get("invalid_reason"),
                "settlement_error": result.get("settlement_error"),
            },
        )

    settlement = result.get("settlement") or {}
    try:
        report = await agent.run_check(city_code=code, address=addr)
    except Exception:  # noqa: BLE001
        log.warning("property-due-diligence join failed after settle", exc_info=True)
        receipt = base64.b64encode(json.dumps(settlement).encode()).decode()
        return JSONResponse(
            status_code=502,
            headers={"PAYMENT-RESPONSE": receipt},
            content={
                "error": "upstream_open_data_unavailable",
                "detail": "payment settled; open-data join failed; contact seller",
                "city": code,
            },
        )

    tx = settlement.get("transaction") or settlement.get("txHash")
    try:
        from app.swarm import ledger_writer

        ledger_writer.record_revenue(
            agent_id=agent.PRODUCT_ID,
            amount_usdc=parse_price_usdc(agent.PRICE),
            network=settings.x402_default_network,
            product_id=agent.PRODUCT_ID,
            tx=str(tx) if tx else None,
            payer=settlement.get("payer"),
        )
    except Exception:  # noqa: BLE001
        log.warning("property-due-diligence revenue ledger write failed", exc_info=True)

    latency = round((time.monotonic() - t0) * 1000)
    log.info(
        "property-due-diligence settled",
        extra={"city": code, "status_code": 200, "latency_ms": latency},
    )
    receipt = base64.b64encode(json.dumps(settlement).encode()).decode()
    return JSONResponse(content=report, headers={"PAYMENT-RESPONSE": receipt})


def _402(payment_required: str) -> JSONResponse:
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
    return JSONResponse(
        status_code=402,
        headers={"PAYMENT-REQUIRED": payment_required},
        content=content,
    )
