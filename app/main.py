"""FastAPI application: HTTP transport, manifest, health, MCP SSE mount."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator, Literal

import httpx

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from pydantic import BaseModel, Field, HttpUrl

from app.commerce import quota_store
from app.config import settings
from app.dashboard import DASHBOARD_HTML
from app.doctor import run_checks
from app.ledger_io import read_ledger_rows
from app.logging_config import setup_logging
from app.manifest import build_mcp_manifest
from app.mcp_server import mcp
from app.models import BuildSellerRequirementsInput, GetPaymentRequirementsInput
from app.ops_events import event_stream, format_sse
from app.payment_rails import build_payment_rails
from app.probe_rate_limit import ProbeRateLimitExceeded, probe_rate_limiter
from app.ssrf_guard import SSRFBlockedError, validate_probe_url
from app.swarm import orchestrator as swarm_orchestrator
from app.swarm.registry import swarm_registry
from app.stripe_payments import (
    StripeNotConfiguredError,
    StripeWebhookError,
    create_checkout_session,
    handle_stripe_webhook,
)
from app import os_monitor, wallet_read, x402_services

setup_logging()
logger = logging.getLogger("x402")
log = logger

# Build the MCP Streamable HTTP app up front so its session manager can run
# inside the FastAPI lifespan (Starlette does not run mounted sub-app lifespans;
# without this every MCP session dies with "Session terminated" at initialize).
try:
    _mcp_http_app = mcp.streamable_http_app()
except AttributeError:
    _mcp_http_app = None


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Run the MCP session manager AND the OS-monitor background sampler.

    Endpoints also sample on demand, so nothing breaks when the lifespan
    doesn't run (e.g. bare TestClient without a context manager).
    """
    sampler = (
        asyncio.create_task(os_monitor.sampler_loop())
        if settings.os_monitor_enabled
        else None
    )
    # Rebuild the pinned listing BEFORE serving: the purchase URL is in the
    # Bazaar catalog, so the first request after a cold start may well be a
    # buyer. Bounded and non-fatal — a slow RPC must not stall the boot.
    if settings.pinned_pulse_product_id:
        from app.swarm import publisher

        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(publisher.restore_pinned_listing(), timeout=45.0)
    try:
        if _mcp_http_app is not None:
            async with mcp.session_manager.run():
                yield
        else:
            yield
    finally:
        if sampler:
            sampler.cancel()
            with suppress(asyncio.CancelledError):
                await sampler


app = FastAPI(
    title="x402 Micropayments MCP",
    description="MCP server for x402 HTTP micropayments with agent-commerce overlay",
    version="0.1.0",
    lifespan=_lifespan,
)

# TODO auth before public exposure — dashboard CORS for local Vite dev only.
_cors_methods = ["GET", "POST"] if settings.dashboard_actions else ["GET"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=_cors_methods,
    allow_headers=["*"],
)


class SellerRequirementsRequest(BaseModel):
    network: str = "eip155:84532"
    pay_to: str | None = None
    price: str = "$0.01"
    scheme: str = "exact"
    description: str = "Paid MCP-backed API access"


class SwarmRunRequest(BaseModel):
    topic: str = Field(description="Research topic for the swarm to buy/compose/list")
    max_price_usdc: float | None = Field(default=None, ge=0)
    agent_id: str | None = None
    allow_paid_inputs: bool | None = Field(
        default=None,
        description="Spend on upstream inputs. Defaults to SWARM_ALLOW_PAID_INPUTS "
        "(off), in which case the cycle synthesizes from free inputs instead.",
    )


class StripeCheckoutRequest(BaseModel):
    agent_id: str | None = Field(
        default=None, description="Agent to credit; auto-generated if omitted"
    )
    purpose: Literal["pro_tier_upgrade", "tool_credits"] = Field(
        description="Purchase type: pro tier or per-use tool credits"
    )
    credits: int | None = Field(
        default=None,
        ge=1,
        description="Credits pack size when purpose is tool_credits",
    )


@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log full detail server-side; do NOT leak exception internals to callers.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An internal error occurred.",
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
        "stripe_configured": bool(settings.stripe_secret_key),
        "pay_to_configured": bool(settings.x402_pay_to_address),
    }


@app.get("/.well-known/mcp")
async def well_known_mcp() -> dict:
    return build_mcp_manifest()


@app.get("/stats")
async def stats_snapshot() -> dict:
    """Mission-control quota snapshot (read-only)."""
    return quota_store.snapshot()


@app.get("/events")
async def tool_events() -> StreamingResponse:
    """SSE stream of MCP tool invocations."""

    async def generate():
        async for event in event_stream():
            yield format_sse(event)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/doctor")
async def doctor_report() -> dict:
    """Machine-readable health checks for setup wizard."""
    return run_checks()


@app.get("/os")
async def os_snapshot(processes: bool = Query(default=False)) -> dict:
    """Host OS telemetry snapshot with ok/warn/critical verdict."""
    return os_monitor.get_os_metrics(include_processes=processes)


@app.get("/os/history")
async def os_history(limit: int = Query(default=120, ge=1, le=720)) -> dict:
    """Rolling OS telemetry history (oldest first)."""
    return {"samples": os_monitor.get_history(limit)}


@app.get("/wallet")
async def wallet_status() -> dict:
    """Public addresses and USDC balances only — no key material."""
    return await wallet_read.build_wallet_snapshot()


@app.get("/probe")
async def probe_url(
    request: Request,
    url: HttpUrl = Query(description="HTTP(S) URL to probe for 402 requirements"),
    method: str = Query(default="GET", description="HTTP method"),
) -> dict:
    """Keyless 402 probe proxy — SSRF-guarded, rate-limited, no MCP quota."""
    client_ip = request.client.host if request.client else "unknown"
    try:
        probe_rate_limiter.check(client_ip)
        validate_probe_url(str(url))
        params = GetPaymentRequirementsInput(url=url, method=method.upper())
        return await x402_services.get_payment_requirements(params)
    except ProbeRateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limit_exceeded", "retry_after": exc.retry_after},
        ) from exc
    except SSRFBlockedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        # Upstream unreachable/timeout — a clean 502, not an opaque 500.
        raise HTTPException(
            status_code=502, detail="upstream probe target unreachable"
        ) from exc


@app.post("/seller/requirements")
async def seller_requirements(body: SellerRequirementsRequest) -> dict:
    """Keyless seller requirements builder — gated behind DASHBOARD_ACTIONS."""
    if not settings.dashboard_actions:
        raise HTTPException(
            status_code=403,
            detail="DASHBOARD_ACTIONS is disabled; dashboard is read-only.",
        )
    params = BuildSellerRequirementsInput(
        network=body.network,
        pay_to=body.pay_to,
        price=body.price,
        scheme=body.scheme,
        description=body.description,
    )
    try:
        return x402_services.build_seller_requirements(params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/ledger/{name}")
async def ledger_rows(name: Literal["spend", "revenue"]) -> list[dict]:
    """Agent-ops spend/revenue ledger (newest first, max 1000)."""
    return read_ledger_rows(name)


@app.get("/swarm/runs")
async def swarm_runs(limit: int = Query(default=50, ge=1, le=200)) -> list[dict]:
    """Recent swarm Agency runs (buy → compose → list), newest first."""
    return swarm_registry.recent_runs(limit)


@app.get("/swarm/products")
async def swarm_products() -> list[dict]:
    """Listed composite products with cost basis, price, and margin."""
    return swarm_registry.products()


@app.get("/security")
async def security() -> dict:
    """Security posture: signing-key provider, seller-only capability, guidance."""
    from app.keyprovider import security_posture

    return security_posture()


@app.get("/swarm/assessment")
async def swarm_assessment() -> dict:
    """Strategic assessment: real signals, scored profit routes, prioritized
    backlog, and human-gated growth items (the swarm's strategic core)."""
    from app.swarm import assessor

    return assessor.assess()


@app.get("/pulse")
async def base_pulse() -> dict:
    """Live Base Network Pulse — synthesized settlement-conditions intelligence."""
    from app import pulse

    return await pulse.get_pulse()


@app.post("/pulse/publish")
async def pulse_publish() -> dict:
    """Synthesize a live Pulse and list it as a payable x402 product."""
    if not settings.dashboard_actions:
        raise HTTPException(
            status_code=403, detail="DASHBOARD_ACTIONS is disabled; publishing is off."
        )
    from app.swarm import publisher

    agent_id = quota_store.resolve_agent_id(None)
    product = await publisher.publish_pulse_product(agent_id)
    base = settings.public_base_url.rstrip("/")
    return {
        "product_id": product.product_id,
        "topic": product.topic,
        "price_usdc": product.price_usdc,
        "network": product.network,
        "pay_to": (product.seller_requirements or {}).get("pay_to"),
        "purchase_url": f"{base}/swarm/products/{product.product_id}/purchase",
    }


@app.post("/swarm/run")
async def swarm_run(body: SwarmRunRequest) -> dict:
    """Run one swarm cycle in-process so the listing is hosted by this server.

    Two independent gates, because they mean different things: SWARM_ENABLED
    says this deployment has a buyer role at all, DASHBOARD_ACTIONS says
    mutating HTTP actions are allowed. A seller-only box wants the first off.
    """
    if not settings.swarm_enabled:
        raise HTTPException(
            status_code=403,
            detail="SWARM_ENABLED is false; the buyer role is off on this deployment.",
        )
    if not settings.dashboard_actions:
        raise HTTPException(
            status_code=403, detail="DASHBOARD_ACTIONS is disabled; running is off."
        )
    agent_id = quota_store.resolve_agent_id(body.agent_id)
    return await swarm_orchestrator.run_swarm_research(
        body.topic, agent_id, body.max_price_usdc, body.allow_paid_inputs
    )


@app.api_route("/swarm/products/{product_id}/purchase", methods=["GET", "POST"])
async def purchase_composite(product_id: str, request: Request) -> JSONResponse:
    """x402-payable endpoint for a listed composite.

    No PAYMENT-SIGNATURE -> HTTP 402 with the PAYMENT-REQUIRED challenge.
    With PAYMENT-SIGNATURE -> verify + settle via the swarm merchant, then
    deliver the composite report and return the PAYMENT-RESPONSE settlement.
    """
    import base64
    import json as _json

    product = swarm_registry.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"unknown product_id: {product_id}")

    seller = product.seller_requirements or {}
    payment_required = seller.get("payment_required_header")
    if not payment_required:
        raise HTTPException(
            status_code=409, detail="product is not listed for sale (no requirements)"
        )

    signature = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get(
        "X-PAYMENT"
    )
    if not signature:
        return JSONResponse(
            status_code=402,
            content={
                "error": "payment_required",
                "product_id": product_id,
                "topic": product.topic,
                "price_usdc": product.price_usdc,
                "network": product.network,
                "pay_to": seller.get("pay_to"),
                "instructions": "Pay via x402 and retry with a PAYMENT-SIGNATURE header.",
            },
            headers={
                "PAYMENT-REQUIRED": payment_required,
                "Access-Control-Expose-Headers": "PAYMENT-REQUIRED,PAYMENT-RESPONSE",
            },
        )

    buyer_agent_id = request.headers.get("X-Agent-Id") or quota_store.resolve_agent_id(
        None
    )
    try:
        result = await swarm_orchestrator.settle_composite_sale(
            product_id, signature, payment_required, buyer_agent_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    headers = {"Access-Control-Expose-Headers": "PAYMENT-RESPONSE"}
    settlement = (result.get("verification") or {}).get("settlement")
    if settlement:
        headers["PAYMENT-RESPONSE"] = base64.b64encode(
            _json.dumps(settlement).encode()
        ).decode()

    return JSONResponse(
        status_code=200,
        content={
            "product_id": product_id,
            "topic": product.topic,
            "report": result.get("report"),
            "revenue_usdc": result.get("revenue_usdc"),
            "cost_basis_usdc": result.get("cost_basis_usdc"),
            "margin_usdc": result.get("margin_usdc"),
            "payment_settled": result.get("payment_settled"),
        },
        headers=headers,
    )


@app.get("/swarm/revenue")
async def swarm_revenue() -> dict:
    """Swarm portfolio revenue intelligence (read-only)."""
    from app.swarm import sovereign

    return sovereign.build_revenue_report()


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
    """Pro tier and per-use credits upgrade — Stripe primary, x402 alternate."""
    manifest = build_mcp_manifest()
    rails = build_payment_rails()
    return {
        "upgrade_url": settings.upgrade_url,
        "tiers": manifest["tiers"],
        "payment_rails": rails,
        "stripe": {
            "checkout_endpoint": "/stripe/checkout",
            "webhook_endpoint": "/stripe/webhook",
            "mcp_tool": "create_stripe_checkout",
            "flow": [
                "1. POST /stripe/checkout or call create_stripe_checkout (MCP)",
                "2. Redirect buyer to checkout_url and complete payment",
                "3. Stripe webhook POST /stripe/webhook fulfills pro tier or credits",
            ],
        },
        "x402_coinbase": {
            "status": "alternate_future_rail",
            "facilitator_url": settings.x402_facilitator_url,
            "discovery_url": settings.cdp_discovery_url,
            "flow": [
                "1. Call get_pro_upgrade_requirements or get_tool_credits_requirements (MCP)",
                "2. Pay via x402 wallet using returned requirements",
                "3. Call activate_pro_tier or purchase_tool_credits with PAYMENT-SIGNATURE",
            ],
        },
        "tool_credits": {
            "pack_size": settings.tool_credit_pack_size,
            "pack_price": settings.tool_credit_pack_price,
            "stripe_tool": "create_stripe_checkout",
            "x402_payment_tool": "get_tool_credits_requirements",
            "x402_purchase_tool": "purchase_tool_credits",
        },
        "mcp_tools": {
            "stripe": ["create_stripe_checkout"],
            "pro_upgrade_x402": ["get_pro_upgrade_requirements", "activate_pro_tier"],
            "tool_credits_x402": [
                "get_tool_credits_requirements",
                "purchase_tool_credits",
            ],
        },
        "manifest": "/.well-known/mcp",
    }


@app.post("/stripe/checkout", response_model=None)
async def stripe_checkout(body: StripeCheckoutRequest) -> dict:
    """Create Stripe Checkout Session for pro tier or tool credits."""
    try:
        agent_id = quota_store.resolve_agent_id(body.agent_id)
        return create_checkout_session(
            agent_id,
            body.purpose,
            credits=body.credits,
        )
    except StripeNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> JSONResponse:
    """Accept Stripe webhooks; verify signature and fulfill commerce."""
    payload = await request.body()
    try:
        result = handle_stripe_webhook(payload, stripe_signature)
        return JSONResponse(status_code=200, content=result)
    except StripeWebhookError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


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

    settlement = result.get("settlement") or {}
    tx = settlement.get("transaction") or settlement.get("txHash")
    try:
        from app.swarm import ledger_writer
        from app.swarm.publisher import parse_price_usdc

        ledger_writer.record_revenue(
            agent_id="mn-property-check",
            amount_usdc=parse_price_usdc(settings.mn_property_check_price),
            network=settings.x402_default_network,
            product_id="mn-property-check",
            tx=str(tx) if tx else None,
        )
    except Exception:  # ledger write must never break paid delivery
        log.warning("mn/property-check revenue ledger write failed", exc_info=True)

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