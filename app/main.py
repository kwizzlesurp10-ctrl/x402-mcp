"""FastAPI application: HTTP transport, manifest, health, MCP SSE mount."""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.commerce import quota_store
from app.config import settings
from app.dashboard import DASHBOARD_HTML
from app.logging_config import setup_logging
from app.manifest import build_mcp_manifest
from app.mcp_server import mcp

setup_logging()
log = logging.getLogger("x402")

# Build the MCP Streamable HTTP app up front so its session manager can run
# inside the FastAPI lifespan (Starlette does not run mounted sub-app lifespans;
# without this every MCP session dies with "Session terminated" at initialize).
try:
    _mcp_http_app = mcp.streamable_http_app()
except AttributeError:
    _mcp_http_app = None


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    if _mcp_http_app is not None:
        async with mcp.session_manager.run():
            yield
    else:
        yield


app = FastAPI(
    title="x402 Micropayments MCP",
    description="MCP server for x402 HTTP micropayments with agent-commerce overlay",
    version="0.1.0",
    lifespan=_lifespan,
)


@app.exception_handler(Exception)
async def generic_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": str(exc),
            "upgrade_url": settings.upgrade_url,
        },
    )


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=307)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Operator terminal: live health, quota meters, tool matrix, revenue paths."""
    # Inject operator token so dashboard JS can auth /quota polls.
    token_js = f"var __OP_TOKEN__={json.dumps(settings.operator_token)};"
    html = DASHBOARD_HTML.replace("/* __INJECT_TOKEN__ */", token_js, 1)
    return HTMLResponse(html)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "x402-micropayments-mcp",
        "x402_facilitator": settings.x402_facilitator_url,
        "wallet_configured": bool(settings.evm_private_key),
        "pay_to_configured": bool(settings.x402_pay_to_address),
    }


@app.get("/.well-known/mcp")
async def well_known_mcp() -> dict:
    return build_mcp_manifest()


@app.get("/quota/{agent_id}", response_model=None)
async def quota_status(request: Request, agent_id: str):
    """Debug endpoint: inspect quota without consuming a call.

    Protected by OPERATOR_TOKEN when set — send ``Authorization: Bearer <token>``.
    """
    if settings.operator_token:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {settings.operator_token}":
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
    snapshot = quota_store.peek(agent_id)
    meta = quota_store.build_meta(snapshot)
    return {"meta": meta.model_dump()}


@app.get("/upgrade")
async def upgrade_info() -> dict:
    """Pro tier and per-use credits upgrade instructions (x402 payment paths)."""
    manifest = build_mcp_manifest()
    return {
        "upgrade_url": settings.upgrade_url,
        "tiers": manifest["tiers"],
        "tool_credits": {
            "pack_size": settings.tool_credit_pack_size,
            "pack_price": settings.tool_credit_pack_price,
            "payment_tool": "get_tool_credits_requirements",
            "purchase_tool": "purchase_tool_credits",
        },
        "payment_flow": [
            "1. Call get_pro_upgrade_requirements or get_tool_credits_requirements (MCP)",
            "2. Pay via x402 wallet using returned requirements",
            "3. Call activate_pro_tier or purchase_tool_credits with PAYMENT-SIGNATURE",
        ],
        "mcp_tools": {
            "pro_upgrade": ["get_pro_upgrade_requirements", "activate_pro_tier"],
            "tool_credits": ["get_tool_credits_requirements", "purchase_tool_credits"],
        },
        "manifest": "/.well-known/mcp",
    }


@app.get("/mn/property-check")
async def mn_property_check(request: Request, address: str) -> JSONResponse:
    """Paid x402 resource: Minneapolis rental compliance snapshot ($0.01 USDC).

    No PAYMENT-SIGNATURE header → 402 with PAYMENT-REQUIRED (x402 v2 wire).
    With payment → verify + settle via facilitator, then serve the report
    with the settlement receipt in PAYMENT-RESPONSE.
    """
    from app import mn_compliance

    t0 = time.monotonic()
    if not settings.x402_pay_to_address:
        return JSONResponse(
            status_code=503,
            content={"error": "seller_not_configured", "detail": "X402_PAY_TO_ADDRESS unset"},
        )
    if not address.strip() or len(address) > 120:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_address", "detail": "address must be 1-120 chars"},
        )

    payment_required = mn_compliance.build_payment_required_header()
    signature = request.headers.get("PAYMENT-SIGNATURE")
    if not signature:
        log.info("mn/property-check 402 (no signature)", extra={"address": address, "status_code": 402})
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_required},
            content={
                "error": "payment_required",
                "resource": mn_compliance.resource_url(),
                "price": settings.mn_property_check_price,
                "network": settings.x402_default_network,
                "description": mn_compliance.RESOURCE_DESCRIPTION,
                "how_to_pay": "Retry with PAYMENT-SIGNATURE header (x402 v2); "
                "requirements are in the PAYMENT-REQUIRED response header.",
            },
        )

    result = await mn_compliance.verify_and_settle(signature, payment_required)
    if not result["is_valid"] or not result["payment_settled"]:
        log.warning("mn/property-check payment invalid", extra={"address": address, "status_code": 402})
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_required},
            content={
                "error": "payment_invalid",
                "invalid_reason": result.get("invalid_reason"),
                "settlement_error": result.get("settlement_error"),
            },
        )

    report = await mn_compliance.check_property(address)
    latency = round((time.monotonic() - t0) * 1000)
    log.info("mn/property-check settled", extra={"address": address, "status_code": 200, "latency_ms": latency})

    import base64
    import json as _json

    receipt = base64.b64encode(_json.dumps(result["settlement"]).encode()).decode()
    return JSONResponse(content=report, headers={"PAYMENT-RESPONSE": receipt})


# Mount MCP Streamable HTTP / SSE transport when available.
if _mcp_http_app is not None:
    app.mount("/mcp", _mcp_http_app)
else:
    try:
        app.mount("/mcp", mcp.sse_app())
    except AttributeError:
        pass