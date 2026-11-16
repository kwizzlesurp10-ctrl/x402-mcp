"""Verify → fetch open data → settle (CDP) for city property-check HTTP paths."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Awaitable, Callable

from fastapi.responses import JSONResponse

from app.city_compliance.models import CitySpec
from app.city_compliance import publish
log = logging.getLogger("x402.city_compliance")

VerifyFn = Callable[[str, str], Awaitable[dict[str, Any]]]
SettleFn = Callable[[str, str], Awaitable[dict[str, Any]]]


async def deliver_paid_city_report(
    *,
    signature: str,
    payment_required: str,
    mod: Any,
    spec: CitySpec,
    address: str,
    product_id: str,
    price: str,
    verify_payment: VerifyFn,
    settle_payment: SettleFn,
    notify_error: Callable[..., None],
    notify_success: Callable[..., None],
    record_revenue: Callable[..., None],
    log_prefix: str,
) -> JSONResponse:
    """Paid city property-check: never settle before upstream data succeeds."""
    verified = await verify_payment(signature, payment_required)
    if not verified.get("is_valid"):
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_required},
            content={
                "error": "payment_invalid",
                "invalid_reason": verified.get("invalid_reason"),
            },
        )

    try:
        raw = await mod.check_property(address)
        report = publish.prepare_city_report(
            raw, spec=spec, address_fallback=address.strip()
        )
    except Exception:
        log.warning("%s upstream failed before settle", log_prefix, exc_info=True)
        notify_error(
            paid=False,
            detail="upstream_open_data_unavailable",
        )
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "60"},
            content={
                "error": "upstream_open_data_unavailable",
                "city": spec.code,
                "detail": (
                    "City open-data join failed; payment was not charged. "
                    "Retry with the same PAYMENT-SIGNATURE."
                ),
                "payment_settled": False,
            },
        )

    result = await settle_payment(signature, payment_required)
    if not result.get("is_valid") or not result.get("payment_settled"):
        log.warning("%s settlement failed after successful join", log_prefix)
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
    tx = settlement.get("transaction") or settlement.get("txHash")
    try:
        record_revenue(
            tx=str(tx) if tx else None,
            payer=settlement.get("payer"),
        )
    except Exception:
        log.warning("%s revenue ledger write failed", log_prefix, exc_info=True)

    notify_success(
        report=report,
        tx=str(tx) if tx else None,
        payer=str(settlement.get("payer")) if settlement.get("payer") else None,
    )
    receipt = base64.b64encode(json.dumps(settlement).encode()).decode()
    return JSONResponse(content=report, headers={"PAYMENT-RESPONSE": receipt})