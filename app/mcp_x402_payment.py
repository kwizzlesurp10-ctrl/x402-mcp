"""Native x402 payment transport for FastMCP tools (MCP _meta keys).

Compatible with the official x402 MCP client flow: unpaid tool calls return
``CallToolResult`` with structured payment requirements; paid retries attach
``x402/payment`` in request ``_meta`` and receive ``x402/payment-response`` on
success. Server-authored commerce terms always win — caller-supplied price,
payTo, or PAYMENT-REQUIRED blobs are never trusted for verify/settle.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from mcp.types import CallToolResult, TextContent
from x402.mcp.constants import MCP_PAYMENT_META_KEY, MCP_PAYMENT_RESPONSE_META_KEY
from x402.schemas import PaymentPayload, PaymentRequirements

from app.commerce import QuotaExceededError, quota_store
from app.commerce_payment import (
    StoredCommerceChallenge,
    validate_commerce_requirements,
)
from app.config import settings
from app import mcp_settlement_store
from app.models import ToolResponse

logger = logging.getLogger("mcp_x402_payment")

CommerceMcpTool = Literal["commerce.activate_pro", "commerce.purchase_credits"]

# In-process idempotency when REDIS_URL is unset (single-worker / dev only).
# Key: composite (payload hash + challenge fingerprint).
_settlement_cache: dict[str, dict[str, Any]] = {}


def clear_mcp_settlement_cache() -> None:
    """Test helper: reset in-memory settlement idempotency cache."""
    _settlement_cache.clear()
    mcp_settlement_store.clear_mcp_settlement_redis_test()


def _challenge_fingerprint(header: str) -> str:
    return mcp_settlement_store.challenge_fingerprint(header)


def _strip_mcp_internal(result: dict[str, Any]) -> dict[str, Any]:
    out = dict(result)
    out.pop("_mcp_meta", None)
    return out


def extract_payment_from_context(ctx: Any) -> dict[str, Any] | None:
    """Read ``x402/payment`` from FastMCP ``Context.request_context.meta``."""
    if ctx is None:
        return None
    try:
        request_meta = ctx.request_context.meta
        if request_meta is not None and request_meta.model_extra:
            raw = request_meta.model_extra.get(MCP_PAYMENT_META_KEY)
            if raw is None:
                return None
            if isinstance(raw, str):
                return json.loads(raw)
            if isinstance(raw, dict):
                return raw
    except (ValueError, AttributeError, json.JSONDecodeError):
        return None
    return None


def _requirements_from_header(payment_required_header: str) -> list[dict[str, Any]]:
    from x402.http import decode_payment_required_header

    pr = decode_payment_required_header(payment_required_header)
    accepts = list(getattr(pr, "accepts", []) or [])
    return [
        a.model_dump(by_alias=True, exclude_none=True) if hasattr(a, "model_dump") else dict(a)
        for a in accepts
    ]


def _payment_requirements_models(header: str) -> list[PaymentRequirements]:
    from x402.http import decode_payment_required_header

    pr = decode_payment_required_header(header)
    return list(getattr(pr, "accepts", []) or [])


def _resource_info(tool_name: str, description: str) -> Any:
    from x402.schemas import ResourceInfo

    return ResourceInfo(
        url=f"mcp://tool/{tool_name}",
        description=description,
        mime_type="application/json",
    )


def build_payment_required_result(
    *,
    tool_name: str,
    challenge_header: str,
    description: str,
    error_message: str = "Payment required",
) -> CallToolResult:
    """MCP 402-shaped tool result (``isError=True``) for @x402/mcp clients."""
    from x402.http import decode_payment_required_header

    pr = decode_payment_required_header(challenge_header)
    accepts = [
        a.model_dump(by_alias=True, exclude_none=True) if hasattr(a, "model_dump") else dict(a)
        for a in list(getattr(pr, "accepts", []) or [])
    ]
    resource = _resource_info(tool_name, description)
    body: dict[str, Any] = {
        "x402Version": 2,
        "accepts": accepts,
        "error": error_message,
        "resource": resource.model_dump(by_alias=True, exclude_none=True),
    }
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(body))],
        structuredContent=body,
        isError=True,
    )


def _idempotency_key(payload: PaymentPayload) -> str:
    try:
        blob = payload.model_dump(by_alias=True, mode="json")
    except TypeError:
        blob = payload.model_dump(by_alias=True)
    canonical = json.dumps(blob, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _min_atomic_for_challenge(challenge: StoredCommerceChallenge) -> int:
    if challenge.purpose == "pro_tier_upgrade":
        raw = str(settings.pro_tier_price).strip().replace("$", "").replace(",", "")
        return int(round(float(raw) * 1_000_000))
    raw = str(settings.tool_credit_pack_price).strip().replace("$", "").replace(",", "")
    return int(round(float(raw) * 1_000_000))


def _validate_authoritative_challenge(challenge: StoredCommerceChallenge) -> list[dict[str, Any]]:
    from app.x402_services import resolve_revenue_network

    reqs = _requirements_from_header(challenge.payment_required_header)
    validate_commerce_requirements(
        reqs,
        min_amount_atomic=_min_atomic_for_challenge(challenge),
        expected_network=resolve_revenue_network(),
    )
    return reqs


async def verify_and_settle_mcp_payload(
    payment_data: dict[str, Any],
    challenge: StoredCommerceChallenge,
) -> dict[str, Any]:
    """Verify + settle using only the server-stored PAYMENT-REQUIRED header."""
    from app.x402_services import _invalid_payment_result, _network_of, _resource_server

    _validate_authoritative_challenge(challenge)

    try:
        payload = PaymentPayload.model_validate(payment_data)
    except Exception as exc:  # noqa: BLE001
        return _invalid_payment_result(f"malformed_payment: {exc}")

    payment_hash = _idempotency_key(payload)
    challenge_fp = _challenge_fingerprint(challenge.payment_required_header)
    composite = mcp_settlement_store.composite_cache_key(
        payment_hash, challenge.payment_required_header
    )

    wants_redis = mcp_settlement_store.redis_required_for_mcp_commerce()
    use_redis = mcp_settlement_store.mcp_commerce_redis_ready()
    if settings.mcp_commerce_redis_strict and wants_redis and not use_redis:
        return _invalid_payment_result("redis_unavailable_mcp_commerce")

    cached_local = _settlement_cache.get(composite)
    if cached_local is not None:
        return _strip_mcp_internal(cached_local)

    if use_redis:
        redis_first = mcp_settlement_store.get_cached_settlement(
            composite, expected_challenge_fp=challenge_fp
        )
        if redis_first is not None:
            _settlement_cache[composite] = redis_first
            return _strip_mcp_internal(redis_first)

    lock_token: str | None = None
    if use_redis:
        acquired, lock_token, lock_redis_error = (
            mcp_settlement_store.acquire_settlement_lock(composite)
        )
        if lock_redis_error:
            return _invalid_payment_result("redis_unavailable_mcp_commerce")
        if not acquired:
            merged = await mcp_settlement_store.wait_for_cached_settlement_async(
                composite,
                expected_challenge_fp=challenge_fp,
            )
            if merged is not None:
                _settlement_cache[composite] = merged
                return _strip_mcp_internal(merged)
            att = mcp_settlement_store.get_attempt_state(composite)
            if att and att.get("status") == "ambiguous_settlement":
                return _invalid_payment_result("settlement_ambiguous_manual_reconciliation")
            return _invalid_payment_result("settlement_contention_timeout")

    try:
        if use_redis:
            again = mcp_settlement_store.get_cached_settlement(
                composite, expected_challenge_fp=challenge_fp
            )
            if again is not None:
                _settlement_cache[composite] = again
                return _strip_mcp_internal(again)
            mcp_settlement_store.set_attempt_state(
                composite,
                {"status": "in_progress", "challenge_fp": challenge_fp},
            )

        accepts = _payment_requirements_models(challenge.payment_required_header)
        if not accepts:
            return _invalid_payment_result("commerce challenge missing accepts[]")

        network = _network_of(accepts[0])
        server = _resource_server(network)
        matched = server.find_matching_requirements(accepts, payload)
        if matched is None:
            return _invalid_payment_result(
                "payment does not match server-authored requirements (payTo/amount/network)"
            )

        try:
            verify_result = await server.verify_payment(payload, matched)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp payment verify failed: %s", type(exc).__name__, exc_info=False)
            return _invalid_payment_result(f"verify_failed: {type(exc).__name__}")

        if not verify_result.is_valid:
            return {
                "is_valid": False,
                "invalid_reason": getattr(verify_result, "invalid_reason", None)
                or "payment_invalid",
                "settlement": None,
                "settlement_error": None,
                "payment_settled": False,
                "facilitator_url": None,
                "sdk": "x402ResourceServer.verify_payment + settle_payment",
            }

        settlement = None
        settlement_error: str | None = None
        try:
            settle_result = await server.settle_payment(payload, matched)
            settlement = settle_result.model_dump(by_alias=True, exclude_none=True)
        except Exception as exc:  # noqa: BLE001
            settlement_error = type(exc).__name__
            logger.warning("mcp settle_payment raised (%s)", settlement_error, exc_info=False)
            if use_redis:
                mcp_settlement_store.set_attempt_state(
                    composite,
                    {
                        "status": "ambiguous_settlement",
                        "reason": "settle_exception",
                        "challenge_fp": challenge_fp,
                    },
                )
            return _invalid_payment_result("settlement_exception_ambiguous")

        settle_success = settlement is not None and settlement.get("success") is True
        tx_recorded = bool(
            (settlement or {}).get("transaction") or (settlement or {}).get("txHash")
        )

        result: dict[str, Any] = {
            "is_valid": True,
            "invalid_reason": None,
            "settlement": settlement,
            "settlement_error": settlement_error,
            "payment_settled": settle_success and tx_recorded,
            "facilitator_url": None,
            "sdk": "x402ResourceServer.verify_payment + settle_payment",
        }

        if settle_success and tx_recorded:
            if use_redis:
                written = mcp_settlement_store.try_cache_settlement(
                    composite, result, challenge_fp=challenge_fp
                )
                if not written:
                    merged = await mcp_settlement_store.wait_for_cached_settlement_async(
                        composite,
                        expected_challenge_fp=challenge_fp,
                    )
                    if merged is not None:
                        _settlement_cache[composite] = merged
                        return _strip_mcp_internal(merged)
                mcp_settlement_store.set_attempt_state(
                    composite,
                    {
                        "status": "succeeded",
                        "challenge_fp": challenge_fp,
                        "tx": str(
                            (settlement or {}).get("transaction")
                            or (settlement or {}).get("txHash")
                            or ""
                        ),
                    },
                )
            _settlement_cache[composite] = result
        elif settle_success and not tx_recorded:
            result["payment_settled"] = False
            result["invalid_reason"] = "settlement_success_without_tx_ambiguous"
            if use_redis:
                mcp_settlement_store.set_attempt_state(
                    composite,
                    {
                        "status": "ambiguous_settlement",
                        "reason": "success_without_tx",
                        "challenge_fp": challenge_fp,
                    },
                )
        elif settlement is not None and settlement.get("success") is False:
            err = (
                settlement.get("errorReason")
                or settlement.get("error")
                or "settlement_failed"
            )
            result["invalid_reason"] = str(err)
            result["payment_settled"] = False
            if use_redis:
                mcp_settlement_store.set_attempt_state(
                    composite,
                    {"status": "failed", "reason": str(err), "challenge_fp": challenge_fp},
                )
        else:
            if use_redis:
                mcp_settlement_store.set_attempt_state(
                    composite,
                    {"status": "ambiguous_settlement", "reason": "null_settlement"},
                )

        return _strip_mcp_internal(result)
    finally:
        if use_redis and lock_token is not None:
            mcp_settlement_store.release_settlement_lock(composite, lock_token)


def _success_call_tool_result(
    payload: ToolResponse,
    settlement: dict[str, Any],
) -> CallToolResult:
    text = json.dumps(payload.model_dump(), indent=2)
    payment_response = settlement.get("settlement") or {}
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        isError=False,
        _meta={MCP_PAYMENT_RESPONSE_META_KEY: payment_response},
    )


async def handle_commerce_mcp_tool(
    tool_name: CommerceMcpTool,
    *,
    agent_id: str | None,
    ctx: Any,
    payment_signature: str | None,
    payment_required: str | None,
    credits: int | None,
    legacy_executor: Callable[[str], Awaitable[dict[str, Any]]],
    mcp_grant: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> str | CallToolResult:
    """Route commerce tools: legacy header params, MCP _meta payment, or 402 challenge."""
    resolved = quota_store.resolve_agent_id(agent_id)

    if payment_signature and payment_required:
        try:
            snapshot = quota_store.consume_quota(resolved)
        except QuotaExceededError as exc:
            return json.dumps({"error": exc.detail, "data": None, "meta": None}, indent=2)
        data = await legacy_executor(resolved)
        from app.ops_events import emit_tool_event

        meta = quota_store.build_meta(snapshot)
        emit_tool_event(tool_name, resolved, meta.model_dump())
        return json.dumps(ToolResponse(data=data, meta=meta).model_dump(), indent=2)

    mcp_payment = extract_payment_from_context(ctx)
    if mcp_payment is None:
        header = _issue_challenge_header(tool_name, resolved, credits)
        desc = (
            f"x402 MCP Pro tier for agent {resolved}"
            if tool_name == "commerce.activate_pro"
            else f"x402 MCP tool credits for agent {resolved}"
        )
        return build_payment_required_result(
            tool_name=tool_name,
            challenge_header=header,
            description=desc,
        )

    try:
        snapshot = quota_store.consume_quota(resolved)
    except QuotaExceededError as exc:
        return build_payment_required_result(
            tool_name=tool_name,
            challenge_header=_issue_challenge_header(tool_name, resolved, credits),
            description="quota exceeded",
            error_message=str(exc.detail.get("error", "quota_exceeded")),
        )

    challenge = resolve_commerce_challenge(tool_name, resolved, credits)
    settlement = await verify_and_settle_mcp_payload(mcp_payment, challenge)
    if not settlement.get("is_valid") or not settlement.get("payment_settled"):
        reason = (
            settlement.get("invalid_reason")
            or settlement.get("settlement_error")
            or "payment_invalid"
        )
        return build_payment_required_result(
            tool_name=tool_name,
            challenge_header=challenge.payment_required_header,
            description="payment rejected",
            error_message=str(reason),
        )

    data = mcp_grant(resolved, settlement)
    from app.ops_events import emit_tool_event

    meta = quota_store.build_meta(snapshot)
    emit_tool_event(tool_name, resolved, meta.model_dump())
    return _success_call_tool_result(ToolResponse(data=data, meta=meta), settlement)


def _issue_challenge_header(
    tool_name: CommerceMcpTool,
    agent_id: str,
    credits: int | None,
) -> str:
    from app import x402_services

    if tool_name == "commerce.activate_pro":
        built = x402_services.build_pro_upgrade_requirements(agent_id)
    else:
        pack = credits or settings.tool_credit_pack_size
        built = x402_services.build_tool_credits_requirements(agent_id, pack)
    header = built.get("payment_required_header")
    if not header:
        raise ValueError("failed to issue commerce payment challenge")
    return header


def resolve_commerce_challenge(
    tool_name: CommerceMcpTool,
    agent_id: str,
    credits: int | None,
) -> StoredCommerceChallenge:
    from app import x402_services

    if tool_name == "commerce.activate_pro":
        return x402_services.resolve_pro_authoritative_header(
            agent_id,
            rebuild=lambda: x402_services.build_pro_upgrade_requirements(agent_id),
        )
    pack = credits or settings.tool_credit_pack_size
    return x402_services.resolve_credits_authoritative_header(
        agent_id,
        pack,
        rebuild=lambda: x402_services.build_tool_credits_requirements(agent_id, pack),
    )
