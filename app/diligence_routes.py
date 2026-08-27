"""HTTP routes for the US rental diligence pack composite task."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import demand, diligence_pack
from app.config import settings

log = logging.getLogger("x402")

router = APIRouter(tags=["tasks"])


def _seller_misconfigured() -> JSONResponse | None:
    if not settings.x402_pay_to_address:
        return JSONResponse(
            status_code=503,
            content={
                "error": "seller_not_configured",
                "detail": "X402_PAY_TO_ADDRESS unset",
            },
        )
    return None


def _challenge_or_503() -> tuple[str | None, JSONResponse | None]:
    try:
        # Validate price clamp before hitting facilitator
        diligence_pack.validated_price_usdc()
        header = diligence_pack.build_payment_required_header()
        return header, None
    except ValueError as exc:
        log.error("diligence pack misconfigured: %s", exc)
        return None, JSONResponse(
            status_code=503,
            content={"error": "seller_misconfigured", "detail": str(exc)},
        )
    except Exception:  # noqa: BLE001
        log.warning("diligence pack: cannot build challenge", exc_info=True)
        return None, JSONResponse(
            status_code=503,
            headers={"Retry-After": "30"},
            content={"error": "challenge_unavailable", "detail": "retry shortly"},
        )


def _402_body(payment_required: str, *, note: str | None = None) -> JSONResponse:
    content: dict[str, Any] = {
        "error": "payment_required",
        "resource": diligence_pack.resource_url(),
        "product_id": diligence_pack.PRODUCT_ID,
        "price": diligence_pack.price_string(),
        "network": settings.x402_default_network,
        "description": diligence_pack.RESOURCE_DESCRIPTION,
        "method": "POST",
        "input_schema": {
            "type": "object",
            "required": ["properties"],
            "properties": {
                "properties": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": settings.diligence_pack_max_properties,
                    "items": {
                        "type": "object",
                        "required": ["city_code", "address"],
                        "properties": {
                            "city_code": {
                                "type": "string",
                                "enum": list(diligence_pack.CITY_CODES),
                            },
                            "address": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 120,
                            },
                        },
                    },
                },
                "include_base_pulse_context": {"type": "boolean", "default": False},
                "idempotency_key": {"type": "string", "maxLength": 64},
            },
        },
        "example": diligence_pack.DISCOVERY_INPUT_EXAMPLE,
        "how_to_pay": (
            "POST JSON body with PAYMENT-SIGNATURE header (x402 v2); "
            "requirements are in the PAYMENT-REQUIRED response header. "
            "Single-address $0.01 tier: GET /us/{code}/property-check."
        ),
    }
    if note:
        content["note"] = note
    return JSONResponse(
        status_code=402,
        headers={"PAYMENT-REQUIRED": payment_required},
        content=content,
    )


@router.get("/tasks/us-rental-diligence")
async def diligence_pack_get(request: Request) -> JSONResponse:
    """Crawler-friendly 402: explains POST body; never 422 before challenge."""
    bad = _seller_misconfigured()
    if bad:
        return bad
    payment_required, err = _challenge_or_503()
    if err:
        return err
    assert payment_required is not None
    if not demand.is_self_traffic(request.headers):
        demand.record_challenge(
            diligence_pack.PRODUCT_ID, request.headers.get("user-agent")
        )
    return _402_body(
        payment_required,
        note="This resource is POST-only. Send JSON body as in `example`.",
    )


@router.post("/tasks/us-rental-diligence")
async def diligence_pack_post(request: Request) -> JSONResponse:
    """Paid multi-city rental diligence pack ($0.75–$2.50, default $1.50)."""
    t0 = time.monotonic()
    bad = _seller_misconfigured()
    if bad:
        return bad

    payment_required, err = _challenge_or_503()
    if err:
        return err
    assert payment_required is not None

    signature = request.headers.get("PAYMENT-SIGNATURE")
    from app.fund_first import GRANT_HEADER, consume_grant, peek_grant

    grant_hdr = request.headers.get(GRANT_HEADER)
    if not signature and not grant_hdr:
        log.info(
            "diligence-pack 402 (no signature)",
            extra={"status_code": 402},
        )
        if not demand.is_self_traffic(request.headers):
            demand.record_challenge(
                diligence_pack.PRODUCT_ID, request.headers.get("user-agent")
            )
        return _402_body(payment_required)

    # Paid path: parse/validate body BEFORE settle/consume so we never charge
    # (or burn a fund-first grant) on bad input.
    try:
        raw = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "detail": "JSON body required",
            },
        )
    if not isinstance(raw, dict):
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "detail": "body must be a JSON object"},
        )
    try:
        body = diligence_pack.DiligencePackRequest.model_validate(raw)
    except ValidationError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "details": exc.errors(include_url=False),
            },
        )

    if grant_hdr:
        peeked = peek_grant(grant_hdr)
        if peeked is None and not signature:
            return JSONResponse(
                status_code=402,
                headers={"PAYMENT-REQUIRED": payment_required},
                content={
                    "error": "payment_rejected",
                    "invalid_reason": "fund_first_grant_invalid_or_used",
                },
            )
        if peeked is not None:
            consumed = consume_grant(grant_hdr)
            if consumed:
                pack = await diligence_pack.build_pack(
                    body,
                    payment_settled=True,
                    settlement={"grant": consumed["ticket_id"]},
                )
                latency = round((time.monotonic() - t0) * 1000)
                log.info(
                    "diligence-pack unlocked by fund-first grant",
                    extra={
                        "status_code": 200,
                        "latency_ms": latency,
                        "ok_count": pack.get("ok_count"),
                        "property_count": pack.get("property_count"),
                    },
                )
                return JSONResponse(content=pack)

    if not signature:
        return _402_body(payment_required)

    result = await diligence_pack.verify_and_settle(signature, payment_required)
    if not result.get("is_valid") or not result.get("payment_settled"):
        log.warning(
            "diligence-pack payment invalid",
            extra={"status_code": 402},
        )
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_required},
            content={
                "error": "payment_rejected",
                "invalid_reason": result.get("invalid_reason"),
                "settlement_error": result.get("settlement_error"),
            },
        )

    settlement = result.get("settlement") or {}
    pack = await diligence_pack.build_pack(
        body, payment_settled=True, settlement=settlement
    )

    tx = settlement.get("transaction") or settlement.get("txHash")
    try:
        from app.swarm import ledger_writer

        ledger_writer.record_revenue(
            agent_id=diligence_pack.PRODUCT_ID,
            amount_usdc=diligence_pack.validated_price_usdc(),
            network=settings.x402_default_network,
            product_id=diligence_pack.PRODUCT_ID,
            tx=str(tx) if tx else None,
            payer=settlement.get("payer"),
        )
    except Exception:  # noqa: BLE001
        log.warning("diligence-pack revenue ledger write failed", exc_info=True)

    latency = round((time.monotonic() - t0) * 1000)
    log.info(
        "diligence-pack settled",
        extra={
            "status_code": 200,
            "latency_ms": latency,
            "ok_count": pack.get("ok_count"),
            "property_count": pack.get("property_count"),
        },
    )

    receipt = base64.b64encode(json.dumps(settlement).encode()).decode()
    return JSONResponse(content=pack, headers={"PAYMENT-RESPONSE": receipt})
