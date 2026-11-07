"""HTTP routes for buyer payment-policy consistency (`POST /x402/policy-check`)."""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import demand, policy_check
from app.config import settings

log = logging.getLogger("x402")

router = APIRouter(tags=["x402"])


def _feature_disabled() -> JSONResponse | None:
    if not settings.policy_check_enabled:
        return JSONResponse(
            status_code=503,
            content={"error": "feature_disabled", "detail": "POLICY_CHECK_ENABLED is false"},
        )
    return None


def _seller_misconfigured() -> JSONResponse | None:
    if not settings.x402_pay_to_address:
        return JSONResponse(
            status_code=503,
            content={"error": "seller_not_configured", "detail": "X402_PAY_TO_ADDRESS unset"},
        )
    return None


def _challenge_or_503() -> tuple[str | None, JSONResponse | None]:
    try:
        header = policy_check.build_payment_required_header()
        return header, None
    except Exception:  # noqa: BLE001
        log.warning("policy-check: cannot build own-service challenge", exc_info=True)
        return None, JSONResponse(
            status_code=503,
            headers={"Retry-After": "30"},
            content={"error": "challenge_unavailable", "detail": "retry shortly"},
        )


def _402_body(payment_required: str) -> JSONResponse:
    content: dict[str, Any] = {
        "error": "payment_required",
        "resource": policy_check.resource_url(),
        "product_id": policy_check.PRODUCT_ID,
        "price": policy_check.price_string(),
        "network": settings.x402_default_network.split(",")[0].strip(),
        "description": policy_check.clamped_description(),
        "method": "POST",
        "input_schema": {
            "type": "object",
            "required": ["payment_required_header", "policy"],
            "properties": {
                "payment_required_header": {
                    "type": "string",
                    "description": "Inspected merchant PAYMENT-REQUIRED header value (base64 wire).",
                },
                "policy": {"type": "object"},
                "request_digest": {"type": "object"},
                "idempotency_key": {"type": "string", "maxLength": 128},
            },
        },
        "example": policy_check.DISCOVERY_INPUT_EXAMPLE,
    }
    return JSONResponse(
        status_code=402,
        headers={"PAYMENT-REQUIRED": payment_required},
        content=content,
    )


@router.post("/x402/policy-check")
async def policy_check_post(request: Request) -> JSONResponse:
    """Paid offline policy inspector. Unpaid → 402; paid → JSON analysis."""
    t0 = time.monotonic()

    fd = _feature_disabled()
    if fd:
        return fd

    bad = _seller_misconfigured()
    if bad:
        return bad

    payment_req_own, err = _challenge_or_503()
    if err:
        return err
    assert payment_req_own is not None

    signature = request.headers.get("PAYMENT-SIGNATURE")

    if not signature:
        if not demand.is_self_traffic(request.headers):
            demand.record_challenge(policy_check.PRODUCT_ID, request.headers.get("user-agent"))
        return _402_body(payment_req_own)

    # Paid path: validate body before settle (validate-then-charge).
    try:
        raw = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "detail": "JSON body required"},
        )
    if not isinstance(raw, dict):
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "detail": "body must be a JSON object"},
        )

    idem_hdr = (request.headers.get("Idempotency-Key") or "").strip()
    if idem_hdr:
        raw = dict(raw)
        raw.setdefault("idempotency_key", idem_hdr)

    try:
        body = policy_check.PolicyCheckBody.model_validate(raw)
    except ValidationError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "details": exc.errors(include_url=False)},
        )

    if body.idempotency_key and policy_check.idempotency_strict_redis_unavailable():
        return JSONResponse(
            status_code=503,
            content={
                "error": "idempotency_store_unavailable",
                "detail": "REDIS_URL configured but unreachable; cannot honor Idempotency-Key safely",
            },
        )

    ok_semantic, sem_detail = policy_check.preflight_semantic_ok(body)
    if not ok_semantic:
        return JSONResponse(
            status_code=422,
            content={"error": "inspected_validation_failed", "detail": sem_detail},
        )

    proof_fp, proof_err = policy_check.payment_proof_fingerprint(signature, payment_req_own)
    if proof_fp is None:
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_req_own},
            content={"error": "malformed_payment", "detail": proof_err or "decode_failed"},
        )

    verified = await policy_check.verify_payment_only(signature, payment_req_own)
    if not verified.get("is_valid"):
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_req_own},
            content={
                "error": "payment_rejected",
                "invalid_reason": verified.get("invalid_reason"),
            },
        )

    payer_fp = policy_check.payer_fingerprint_from_decoded_proof(signature, payment_req_own)
    if payer_fp is None:
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_req_own},
            content={"error": "malformed_payment", "detail": "cannot_bind_payer"},
        )

    input_digest = policy_check.analysis_input_digest(
        inspected_header_digest=policy_check.inspected_header_digest(body.payment_required_header),
        policy=body.policy,
        request_digest=body.request_digest,
    )
    claim_key = policy_check.policy_check_claim_key(body, payer_fp=payer_fp, proof_fp=proof_fp)

    claim_st, claim_rec = await policy_check.delivery_try_claim_or_hit_async(claim_key, input_digest)
    if claim_st == "redis_error":
        return JSONResponse(
            status_code=503,
            content={
                "error": "delivery_store_unavailable",
                "detail": "REDIS_URL configured but unreachable; cannot claim delivery slot safely",
            },
        )
    if claim_st == "conflict":
        return JSONResponse(
            status_code=409,
            content={
                "error": "idempotency_conflict",
                "detail": "same idempotency scope with different analysis inputs",
            },
        )
    if claim_st == "final_hit" and claim_rec and isinstance(claim_rec.get("body"), dict):
        latency = round((time.monotonic() - t0) * 1000)
        log.info(
            "policy-check delivery replay (no settle)",
            extra={"status_code": 200, "latency_ms": latency, "product": policy_check.PRODUCT_ID},
        )
        return JSONResponse(content=claim_rec["body"])

    if claim_st == "claimed_busy":
        waited = await policy_check.delivery_wait_for_final_async(claim_key, input_digest)
        if isinstance(waited, dict):
            latency = round((time.monotonic() - t0) * 1000)
            log.info(
                "policy-check concurrent replay (no second settle)",
                extra={"status_code": 200, "latency_ms": latency, "product": policy_check.PRODUCT_ID},
            )
            return JSONResponse(content=waited)
        return JSONResponse(
            status_code=503,
            content={
                "error": "delivery_in_progress",
                "detail": "identical payment in flight; retry with same proof shortly",
            },
        )

    settle = await policy_check.settle_payment_only(signature, payment_req_own)
    if not settle.get("is_valid") or not settle.get("payment_settled"):
        policy_check.delivery_abort_claim_sync(claim_key)

        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_req_own},
            content={
                "error": "payment_rejected",
                "invalid_reason": settle.get("invalid_reason"),
                "settlement_error": settle.get("settlement_error"),
            },
        )

    settlement = settle.get("settlement") or {}
    tx = settlement.get("transaction") or settlement.get("txHash")
    payer = settlement.get("payer")

    if settle.get("payment_settled") and not tx:
        policy_check.delivery_abort_claim_sync(claim_key)
        return JSONResponse(
            status_code=402,
            content={
                "error": "settlement_ambiguous",
                "detail": "settlement accepted without transaction id; manual reconciliation",
            },
        )

    out = policy_check.build_paid_analysis_dict(body, settlement=settlement)
    written, _prev = await policy_check.delivery_write_final_async(
        claim_key,
        input_digest=input_digest,
        body=out,
        payment_proof_fp=proof_fp,
    )
    if not written:
        policy_check.delivery_abort_claim_sync(claim_key)
        return JSONResponse(
            status_code=503,
            content={
                "error": "delivery_persist_failed",
                "detail": "settlement succeeded but durable delivery record failed — reconcile",
            },
        )

    try:
        from app.swarm import ledger_writer

        ledger_writer.record_revenue(
            agent_id=policy_check.PRODUCT_ID,
            amount_usdc=policy_check.parse_price_usdc(),
            network=settings.x402_default_network.split(",")[0].strip(),
            product_id=policy_check.PRODUCT_ID,
            tx=str(tx) if tx else None,
            payer=str(payer) if payer else None,
        )
    except Exception:  # noqa: BLE001
        log.warning("policy-check revenue ledger write failed", exc_info=True)

    latency = round((time.monotonic() - t0) * 1000)
    log.info(
        "policy-check settled",
        extra={
            "status_code": 200,
            "latency_ms": latency,
            "verdict": out.get("verdict"),
            "accepts": out.get("accepts_evaluated"),
        },
    )

    receipt = base64.b64encode(json.dumps(settlement).encode()).decode()
    return JSONResponse(content=out, headers={"PAYMENT-RESPONSE": receipt})
