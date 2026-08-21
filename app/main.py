"""FastAPI application: HTTP transport, manifest, health, MCP SSE mount."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncIterator, Literal

import httpx

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl

from app.commerce import quota_store
from app.config import settings
from app.dashboard import DASHBOARD_HTML
from app.doctor import run_checks
from app import ledger_io
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
from app import demand, os_monitor, wallet_read, x402_services

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

# Dashboard CORS: local Vite only + exact extras (no free-tunnel wildcards).
def _cors_origins() -> list[str]:
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]
    extra = getattr(settings, "cors_extra_origins", "") or ""
    origins.extend(o.strip().rstrip("/") for o in extra.split(",") if o.strip())
    return origins


_cors_methods = ["GET", "POST"] if settings.dashboard_actions else ["GET"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=_cors_methods,
    allow_headers=["*"],
    expose_headers=["PAYMENT-REQUIRED", "PAYMENT-RESPONSE", "PAYMENT-SIGNATURE"],
)

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0", "[::1]", "::1")


def _public_base_from_request(request: Request) -> str:
    """Public origin for seller resource URLs baked into signed 402 challenges.

    Forwarded headers are only honoured when TRUST_FORWARDED_HOST is set.
    """
    if not settings.trust_forwarded_host:
        return settings.public_base_url.rstrip("/")

    xf_proto = request.headers.get("x-forwarded-proto")
    xf_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if not xf_host:
        return settings.public_base_url.rstrip("/")

    host = xf_host.split(",")[0].strip()
    if host.startswith("["):  # bracketed IPv6, optionally with :port
        bare = host[: host.index("]") + 1] if "]" in host else host
    else:
        bare = host.rsplit(":", 1)[0]
    if bare.lower() in _LOOPBACK_HOSTS or host.lower() in _LOOPBACK_HOSTS:
        return settings.public_base_url.rstrip("/")

    scheme = (xf_proto or "https").split(",")[0].strip()
    return f"{scheme}://{host}".rstrip("/")


# Standalone pilot of the x402 SDK's own FastAPI payment middleware — see
# app/x402_middleware_pilot.py. Purely additive: only GET /pilot/ping is
# gated, every other route is unaffected.
from app import x402_middleware_pilot  # noqa: E402
from app.city_compliance.routes import router as city_compliance_router  # noqa: E402
from app.diligence_routes import router as diligence_router  # noqa: E402

x402_middleware_pilot.register(app)
app.include_router(city_compliance_router)
app.include_router(diligence_router)


def _public_openapi() -> dict:
    """Serve the discovery document, not FastAPI's inventory of every route.

    `/openapi.json` is the FIRST thing x402scan reads about a seller, ahead of
    /.well-known/x402 — see app/openapi_spec.py for what the untouched
    generated version was telling them. Not cached (no `app.openapi_schema`
    assignment): prices come from live config, and a cached spec can drift from
    what is actually being charged.
    """
    from app import openapi_spec

    return openapi_spec.tighten(
        get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
    )


app.openapi = _public_openapi  # type: ignore[method-assign]


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


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """Homepage HTML so domain/app ownership meta tags are scrapable at /.

    Scrapers (Base Build metadata verification, etc.) often only fetch `/` and
    may not follow a bare 307. Keep a soft redirect for humans.
    """
    return HTMLResponse(
        """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="base:app_id" content="6a7018e2a8c4f2b6db3b3e71" />
<title>x402 MCP Storefront</title>
<meta http-equiv="refresh" content="0; url=/dashboard">
<link rel="canonical" href="/dashboard">
</head>
<body>
<p>x402 MCP Storefront — <a href="/dashboard">open mission control</a>.</p>
</body>
</html>
""",
        headers={"Cache-Control": "no-store"},
    )


# Directories render a seller's favicon next to its listing — x402scan pulls
# `<origin>/favicon` for every resource on its index page, and their discovery
# auditor warns when there isn't one. Inline SVG so there is no binary asset to
# ship, no extra request path, and nothing to go stale.
_FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="12" fill="#0b1020"/>'
    '<text x="32" y="42" font-family="ui-monospace,monospace" font-size="26" '
    'font-weight="700" fill="#4ade80" text-anchor="middle">402</text></svg>'
)


@app.get("/favicon.svg", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(
        content=_FAVICON,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# Mission Control SPA (same layout as Vercel). Built into app/static/mission_control
# (Docker multi-stage or local `pnpm build` + copy). Falls back to the legacy
# single-file terminal if the SPA bundle is missing (e.g. partial checkouts).
_MC_DIST = Path(__file__).resolve().parent / "static" / "mission_control"
_BASE_APP_ID_META = '<meta name="base:app_id" content="6a7018e2a8c4f2b6db3b3e71" />'


def _mission_control_html() -> str:
    index_path = _MC_DIST / "index.html"
    if index_path.is_file():
        html = index_path.read_text(encoding="utf-8")
        if "base:app_id" not in html:
            html = html.replace("<head>", f"<head>\n{_BASE_APP_ID_META}", 1)
        return html
    token_js = f"var __OP_TOKEN__={json.dumps(settings.operator_token)};"
    return DASHBOARD_HTML.replace("/* __INJECT_TOKEN__ */", token_js, 1)


@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/dashboard/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """React Mission Control SPA (Vercel layout), same-origin API."""
    return HTMLResponse(
        _mission_control_html(),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/dashboard/legacy", response_class=HTMLResponse)
async def dashboard_legacy() -> HTMLResponse:
    """Previous single-file operator terminal (kept for rollback/compare)."""
    token_js = f"var __OP_TOKEN__={json.dumps(settings.operator_token)};"
    html = DASHBOARD_HTML.replace("/* __INJECT_TOKEN__ */", token_js, 1)
    return HTMLResponse(html)


@app.get("/health")
async def health() -> dict:
    # Report the facilitator actually used for the revenue network, not the
    # raw default. settings.x402_facilitator_url is x402.org (testnet-only),
    # while mainnet settles route to CDP — publishing the default next to a
    # /.well-known/x402 advertising eip155:8453 hands the trust scanners that
    # read this endpoint a mainnet/testnet contradiction.
    from app.x402_services import _facilitator_url_for, resolve_revenue_network

    revenue_network = resolve_revenue_network()
    return {
        "status": "ok",
        "service": "x402-micropayments-mcp",
        "x402_facilitator": _facilitator_url_for(revenue_network),
        "x402_facilitator_network": revenue_network,
        "wallet_configured": bool(settings.evm_private_key),
        "stripe_configured": bool(settings.stripe_secret_key),
        "pay_to_configured": bool(settings.x402_pay_to_address),
        "ownership_proofs_configured": bool(settings.ownership_proofs),
    }


@app.get("/.well-known/mcp")
async def well_known_mcp() -> dict:
    return build_mcp_manifest()


@app.get("/.well-known/x402")
async def well_known_x402() -> dict:
    """Machine manifest of the paid surface, built from live config."""
    from app import agent_surface

    return agent_surface.well_known_x402()


@app.get("/.well-known/agents.json")
async def well_known_agents_json() -> dict:
    """Standard Agents Registry Manifest (Agentic.Market / Open Agent Registry)."""
    from app import agent_surface

    return agent_surface.agents_json()


@app.get("/.well-known/mcp/server-card.json")
async def well_known_mcp_server_card() -> dict:
    """Remote MCP Server Card for Smithery.ai, Glama.ai, and client introspectors."""
    from app import agent_surface

    return agent_surface.mcp_server_card()


@app.get("/.well-known/agent-card.json")
async def well_known_agent_card() -> dict:
    """A2A Protocol v1.0 Agent Card (ecosystem discovery)."""
    from app import agent_surface

    return agent_surface.agent_card()


@app.get("/.well-known/agent.json")
async def well_known_agent_json() -> dict:
    """Legacy A2A Agent Card path; same payload as agent-card.json."""
    from app import agent_surface

    return agent_surface.agent_card()


@app.get("/llms.txt", response_class=PlainTextResponse)
async def llms_txt() -> str:
    """Agent-facing docs: endpoints, prices, and the failure modes that matter."""
    from app import agent_surface

    return agent_surface.llms_txt()


from datetime import datetime, timedelta
import asyncio

_stats_cache = {"time": None, "data": None}

@app.get("/stats")
async def stats_snapshot() -> dict:
    """Mission-control quota snapshot (read-only)."""
    now = datetime.now()
    if _stats_cache["time"] and now - _stats_cache["time"] < timedelta(seconds=10):
        return _stats_cache["data"]
    data = quota_store.snapshot()
    _stats_cache["time"] = now
    _stats_cache["data"] = data
    return data


@app.get("/events")
async def tool_events() -> StreamingResponse:
    """SSE stream of MCP tool invocations."""

    async def generate():
        async for event in event_stream():
            yield format_sse(event)

    return StreamingResponse(generate(), media_type="text/event-stream")


_doctor_cache = {"time": None, "data": None}

@app.get("/doctor")
async def doctor_report() -> dict:
    """Machine-readable health checks for setup wizard."""
    now = datetime.now()
    if _doctor_cache["time"] and now - _doctor_cache["time"] < timedelta(seconds=10):
        return _doctor_cache["data"]
    data = run_checks()
    _doctor_cache["time"] = now
    _doctor_cache["data"] = data
    return data


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


# 10s in-process TTL: dashboard polls hammered Redis free-tier (500k cmds).
# Cache RAW rows only; annotate is_operator_settle on every response so wallet
# config changes never stick a wrong label. Writers must call invalidate.
_ledger_cache: dict[str, dict] = {
    "spend": {"time": None, "data": None},
    "revenue": {"time": None, "data": None},
}


def invalidate_ledger_cache(name: str | None = None) -> None:
    """Drop cached ledger rows so the next read hits the store once.

    Call from append paths after a real write. Does not increase steady-state
    Redis traffic — only the next dashboard poll after a sale refreshes.
    """
    names = (name,) if name in ("spend", "revenue") else ("spend", "revenue")
    for key in names:
        _ledger_cache[key] = {"time": None, "data": None}


@app.get("/ledger/{name}")
async def ledger_rows(name: Literal["spend", "revenue"]) -> list[dict]:
    """Agent-ops spend/revenue ledger (newest first, max 1000).

    Revenue rows are annotated with `is_operator_settle`: True when the row's
    `payer` matches a configured operator wallet (cataloging/re-indexing, not
    a customer), False when it's a different wallet (a real external sale),
    and None when `payer` is missing — rows written before this field existed,
    or a settlement whose facilitator didn't report one. Treat None as
    "unknown", never as "external": most of this project's revenue history is
    self-settled, and the honest default is not to overclaim a sale.
    """
    now = datetime.now()
    cache = _ledger_cache[name]
    if cache["time"] and cache["data"] is not None and now - cache["time"] < timedelta(
        seconds=10
    ):
        rows = cache["data"]
    else:
        rows = read_ledger_rows(name)
        cache["time"] = now
        # Shallow-copy list so later annotation cannot poison the cache entry.
        cache["data"] = list(rows)

    if name != "revenue":
        return list(rows)

    operator_wallets = ledger_io.operator_wallet_set()
    out: list[dict] = []
    for row in rows:
        annotated = dict(row)
        annotated["is_operator_settle"] = ledger_io.classify_operator_settle(
            annotated, operator_wallets
        )
        out.append(annotated)
    return out



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


@app.get("/swarm/products/{product_id}/purchase", operation_id="purchase_composite_get")
@app.post("/swarm/products/{product_id}/purchase", operation_id="purchase_composite_post")
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
        if not demand.is_self_traffic(request.headers):
            demand.record_challenge(product_id, request.headers.get("user-agent"))
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


@app.get("/demand")
async def demand_report() -> dict:
    """Sales funnel: 402 challenges served vs sales settled, per resource."""
    return demand.build_report()


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


@app.get("/mn/property-check/sample")
async def mn_property_check_sample() -> JSONResponse:
    """Free fixed-address sample of the paid MN rental-compliance product.

    Mirrors the /pulse free-preview pattern: agents can verify response shape
    and live ArcGIS join quality before paying. Only SAMPLE_ADDRESS is served
    here — any other address still requires x402 payment on /mn/property-check.
    Does not touch payment, demand counters, or the challenge cache.
    """
    from app import mn_compliance

    report = await mn_compliance.check_property(mn_compliance.SAMPLE_ADDRESS)
    return JSONResponse(
        content={
            "sample": True,
            "sample_address": mn_compliance.SAMPLE_ADDRESS,
            "note": (
                "Free fixed-address sample of the live join (3 City of Minneapolis "
                "ArcGIS datasets). Query any other Minneapolis street address at "
                f"{mn_compliance.resource_url()} for "
                f"{settings.mn_property_check_price} USDC (x402 on Base)."
            ),
            "paid_endpoint": mn_compliance.resource_url(),
            "price": settings.mn_property_check_price,
            "report": report,
        }
    )


@app.get("/mn/property-check")
async def mn_property_check(
    request: Request,
    address: str | None = Query(
        default=None, description="Minneapolis street address, 1-120 chars"
    ),
) -> JSONResponse:
    """Paid x402 resource: Minneapolis rental compliance snapshot ($0.01 USDC).

    No PAYMENT-SIGNATURE header → 402 with PAYMENT-REQUIRED (x402 v2 wire).
    With payment → verify + settle via facilitator, then serve the report
    with the settlement receipt in PAYMENT-RESPONSE.

    `address` is optional at the signature level and validated *after* the
    unpaid branch on purpose: a discovery crawler probes with no parameters at
    all, and FastAPI's own 422 would fire before this function ever ran. "402
    expected, got 400/422 from request validation running before the payment
    challenge" is on x402scan's published list of registration failures, and
    this endpoint has never been indexed by any catalog. The charge order is
    unchanged — validation still runs before verify+settle, so a paying caller
    with a bad address is rejected without being charged.
    """
    from app import mn_compliance

    t0 = time.monotonic()
    if not settings.x402_pay_to_address:
        return JSONResponse(
            status_code=503,
            content={"error": "seller_not_configured", "detail": "X402_PAY_TO_ADDRESS unset"},
        )

    try:
        payment_required = mn_compliance.build_payment_required_header()
    except Exception:  # never seen a cache: facilitator down on a cold start
        log.warning("mn/property-check: cannot build challenge", exc_info=True)
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "30"},
            content={"error": "challenge_unavailable", "detail": "retry shortly"},
        )
    signature = request.headers.get("PAYMENT-SIGNATURE")
    if not signature:
        log.info("mn/property-check 402 (no signature)", extra={"address": address, "status_code": 402})
        if not demand.is_self_traffic(request.headers):
            demand.record_challenge("mn-property-check", request.headers.get("user-agent"))
        base = settings.public_base_url.rstrip("/")
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_required},
            content={
                "error": "payment_required",
                "resource": mn_compliance.resource_url(),
                "price": settings.mn_property_check_price,
                "network": settings.x402_default_network,
                "description": mn_compliance.RESOURCE_DESCRIPTION,
                "sample_url": f"{base}/mn/property-check/sample",
                "how_to_pay": "Retry with PAYMENT-SIGNATURE header (x402 v2); "
                "requirements are in the PAYMENT-REQUIRED response header. "
                "Free fixed-address sample (no payment): GET /mn/property-check/sample.",
            },
        )

    # Paid caller: validate before spending their money, never after.
    if address is None or not address.strip() or len(address) > 120:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_address", "detail": "address must be 1-120 chars"},
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
            payer=settlement.get("payer"),
        )
    except Exception:  # ledger write must never break paid delivery
        log.warning("mn/property-check revenue ledger write failed", exc_info=True)

    import base64
    import json as _json

    receipt = base64.b64encode(_json.dumps(result["settlement"]).encode()).decode()
    return JSONResponse(content=report, headers={"PAYMENT-RESPONSE": receipt})


@app.get("/base/tx-decision")
async def base_tx_decision(
    request: Request,
    gas: str = Query(
        default="usdc",
        description="Gas preset (eth|usdc|erc20|x402) or a custom integer of gas units",
    ),
    urgency: str = Query(
        default="flexible",
        description="now = fee only, always submit; soon = time-sensitive; "
        "flexible = wait for a cheap window",
    ),
) -> JSONResponse:
    """Paid x402 resource: per-transaction submit/wait + fee decision ($0.01).

    The loop-resident tier of the Pulse: bots call this before every send.
    Same wire protocol as /mn/property-check — 402 without a signature,
    verify + settle + deliver with one.
    """
    from app import tx_decision

    t0 = time.monotonic()
    if not settings.x402_pay_to_address:
        return JSONResponse(
            status_code=503,
            content={"error": "seller_not_configured", "detail": "X402_PAY_TO_ADDRESS unset"},
        )
    # Case-insensitive, like gas: an agent sending urgency=NOW is a buyer, not
    # a bad request. Rejecting reasonable capitalization loses the sale.
    urgency = urgency.strip().lower()
    if urgency not in tx_decision.URGENCIES:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_urgency", "detail": f"urgency must be one of {tx_decision.URGENCIES}"},
        )
    gas_units = tx_decision.GAS_PRESETS.get(gas.strip().lower())
    if gas_units is None:
        try:
            gas_units = int(gas)
        except ValueError:
            gas_units = -1
        if not 21_000 <= gas_units <= 30_000_000:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "invalid_gas",
                    "detail": "gas must be eth|usdc|erc20|x402 or an integer in [21000, 30000000]",
                },
            )

    try:
        payment_required = tx_decision.build_payment_required_header()
    except Exception:  # never seen a cache: facilitator down on a cold start
        log.warning("base/tx-decision: cannot build challenge", exc_info=True)
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "30"},
            content={"error": "challenge_unavailable", "detail": "retry shortly"},
        )
    signature = request.headers.get("PAYMENT-SIGNATURE")
    if not signature:
        if not demand.is_self_traffic(request.headers):
            demand.record_challenge("base-tx-decision", request.headers.get("user-agent"))
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_required},
            content={
                "error": "payment_required",
                "resource": tx_decision.resource_url(),
                "price": settings.tx_decision_price,
                "network": settings.x402_default_network,
                "description": tx_decision.RESOURCE_DESCRIPTION,
                "how_to_pay": "Retry with PAYMENT-SIGNATURE header (x402 v2); "
                "requirements are in the PAYMENT-REQUIRED response header.",
            },
        )

    result = await tx_decision.verify_and_settle(signature, payment_required)
    if not result["is_valid"] or not result["payment_settled"]:
        log.warning("base/tx-decision payment invalid", extra={"status_code": 402})
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_required},
            content={
                "error": "payment_invalid",
                "invalid_reason": result.get("invalid_reason"),
                "settlement_error": result.get("settlement_error"),
            },
        )

    decision = await tx_decision.advise(gas_units, urgency)
    latency = round((time.monotonic() - t0) * 1000)
    log.info("base/tx-decision settled", extra={"status_code": 200, "latency_ms": latency})

    settlement = result.get("settlement") or {}
    tx = settlement.get("transaction") or settlement.get("txHash")
    try:
        from app.swarm import ledger_writer
        from app.swarm.publisher import parse_price_usdc

        ledger_writer.record_revenue(
            agent_id="base-tx-decision",
            amount_usdc=parse_price_usdc(settings.tx_decision_price),
            network=settings.x402_default_network,
            product_id="base-tx-decision",
            tx=str(tx) if tx else None,
            payer=settlement.get("payer"),
        )
    except Exception:  # ledger write must never break paid delivery
        log.warning("base/tx-decision revenue ledger write failed", exc_info=True)

    import base64
    import json as _json

    receipt = base64.b64encode(_json.dumps(result["settlement"]).encode()).decode()
    return JSONResponse(content=decision, headers={"PAYMENT-RESPONSE": receipt})


# ---------- Seller demo: paid resource at /demo/paid ----------

# Full challenge payloads keyed by fingerprint (header string alone is not enough
# for the 402 JSON body). Cleared alongside challenge_cache.clear() in tests.
_demo_paid_built: dict[str, dict] = {}


@app.get("/demo/paid")
async def demo_paid_resource(request: Request) -> JSONResponse:
    """Seller demo — 402 without payment; paid body after verify+settle.

    Self-test (vault pays itself on Base Sepolia):
      pay_and_fetch url=http://127.0.0.1:8402/demo/paid preferred_network=eip155:84532
    """
    from app import challenge_cache

    if not settings.x402_pay_to_address:
        return JSONResponse(
            status_code=503,
            content={
                "error": "seller_not_configured",
                "detail": "X402_PAY_TO_ADDRESS unset",
            },
        )

    resource_url = f"{_public_base_from_request(request)}/demo/paid"
    description = "x402 seller demo — paid JSON secret on Base Sepolia"
    price = settings.x402_default_price
    network = settings.x402_default_network

    # Fingerprint every input baked into the header (description included).
    fp = challenge_cache.fingerprint(
        resource_url=resource_url,
        description=description,
        price=price,
        network=network,
        pay_to=settings.x402_pay_to_address,
        scheme="exact",
        include_bazaar=True,
    )

    built = _demo_paid_built.get(fp)
    if built is None:
        # Cache-miss path: build once, then pin header + full payload.
        # challenge_cache.get_or_build only stores the header string; we keep
        # the richer dict so the 402 JSON body stays correct without rebuilds.
        try:

            def _header_builder() -> str:
                # Synchronous entry for get_or_build; we never call this when
                # the async path below already built — only on degrade rebuilds.
                raise RuntimeError("async build required")

            # Fast path: header already cached under this fingerprint.
            cached_entry = challenge_cache._load("demo-paid")  # noqa: SLF001
            if cached_entry and cached_entry.get("fp") == fp and cached_entry.get("header"):
                built = {
                    "payment_required": {},
                    "payment_required_header": cached_entry["header"],
                    "pay_to": settings.x402_pay_to_address,
                    "price": price,
                    "network": network,
                }
            else:
                built = await x402_services.build_payment_required_for_resource(
                    resource_url=resource_url,
                    description=description,
                    price=price,
                    network=network,
                )
                challenge_cache.get_or_build(
                    "demo-paid",
                    fp,
                    lambda h=built["payment_required_header"]: h,
                )
                _demo_paid_built[fp] = built
        except Exception:
            # Stale header beats no 402 (indexer drops non-402 endpoints).
            stale = challenge_cache._load("demo-paid")  # noqa: SLF001
            if stale and stale.get("header"):
                log.warning(
                    "demo/paid: build failed; serving last-known-good challenge",
                    exc_info=True,
                )
                built = {
                    "payment_required": {},
                    "payment_required_header": stale["header"],
                    "pay_to": settings.x402_pay_to_address,
                    "price": price,
                    "network": network,
                }
            else:
                log.warning("demo/paid: cannot build challenge", exc_info=True)
                return JSONResponse(
                    status_code=503,
                    headers={"Retry-After": "30"},
                    content={
                        "error": "challenge_unavailable",
                        "detail": "retry shortly",
                    },
                )
    else:
        # Touch challenge_cache so the header stays warm for restart survival.
        challenge_cache.get_or_build(
            "demo-paid",
            fp,
            lambda h=built["payment_required_header"]: h,
        )

    payment_sig = (
        request.headers.get("PAYMENT-SIGNATURE")
        or request.headers.get("X-PAYMENT")
        or request.headers.get("payment-signature")
    )

    if not payment_sig:
        return JSONResponse(
            status_code=402,
            content={
                **(built.get("payment_required") or {}),
                "note": "Pay with x402 exact scheme, then retry with PAYMENT-SIGNATURE header.",
                "seller_pay_to": built["pay_to"],
                "price": built["price"],
                "network": built["network"],
            },
            headers={
                "PAYMENT-REQUIRED": built["payment_required_header"],
                "Access-Control-Expose-Headers": "PAYMENT-REQUIRED",
            },
        )

    result = await x402_services.verify_and_settle_from_headers(
        payment_signature=payment_sig,
        payment_required_header=built["payment_required_header"],
    )

    if not result.get("is_valid"):
        return JSONResponse(
            status_code=402,
            content={
                **(built.get("payment_required") or {}),
                "error": "Payment verification failed",
                "invalid_reason": result.get("invalid_reason"),
            },
            headers={"PAYMENT-REQUIRED": built["payment_required_header"]},
        )

    settlement = result.get("settlement") or {}
    paid_ok = result.get("payment_settled") is True

    if paid_ok:
        try:
            from app.swarm import ledger_writer
            from app.swarm.publisher import parse_price_usdc

            ledger_writer.record_revenue(
                agent_id="seller-demo",
                amount_usdc=parse_price_usdc(built["price"]),
                network=built["network"],
                product_id="seller-demo",
                tx=settlement.get("transaction") or settlement.get("txHash"),
                payer=settlement.get("payer"),
            )
        except Exception:
            log.warning("demo/paid revenue ledger write failed", exc_info=True)

    headers: dict[str, str] = {}
    if paid_ok and settlement:
        try:
            import base64
            import json as _json

            headers["PAYMENT-RESPONSE"] = base64.b64encode(
                _json.dumps(settlement).encode()
            ).decode()
            headers["Access-Control-Expose-Headers"] = "PAYMENT-RESPONSE"
        except Exception:
            pass

    return JSONResponse(
        status_code=200 if paid_ok else 402,
        content={
            "ok": paid_ok,
            "message": "Payment settled — seller demo payload unlocked"
            if paid_ok
            else "Verified but settlement failed",
            "secret": "x402-seller-demo-ok" if paid_ok else None,
            "seller_pay_to": built["pay_to"],
            "price": built["price"],
            "network": built["network"],
            "payment_settled": paid_ok,
            "settlement": settlement,
            "settlement_error": result.get("settlement_error"),
        },
        headers=headers,
    )


@app.get("/demo/paid/info")
async def demo_paid_info(request: Request) -> dict:
    """Free metadata for the seller demo resource (no payment)."""
    base = _public_base_from_request(request)
    return {
        "resource": f"{base}/demo/paid",
        "price": settings.x402_default_price,
        "network": settings.x402_default_network,
        "pay_to": settings.x402_pay_to_address,
        "public_base_url_config": settings.public_base_url,
        "flow": [
            "1. GET /demo/paid → 402 + PAYMENT-REQUIRED",
            "2. Buyer pays (pay_and_fetch or wallet)",
            "3. GET /demo/paid with PAYMENT-SIGNATURE → 200 + secret + settle",
        ],
        "self_test": {
            "url": f"{base}/demo/paid",
            "tool": "pay_and_fetch",
            "preferred_network": settings.x402_default_network,
        },
        "bazaar": {
            "merchant_discovery": (
                "https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant"
                f"?payTo={settings.x402_pay_to_address or ''}"
            ),
            "note": "CDP indexes after settle through CDP facilitator; catalog lag ~10m",
        },
    }


@app.get("/ops/status")
async def ops_status() -> dict:
    """Compact stack status for restart scripts and dashboards."""
    report = run_checks()
    checks = report.get("checks") or []
    return {
        "service": "x402-micropayments-mcp",
        "public_base_url": settings.public_base_url,
        "pay_to": settings.x402_pay_to_address,
        "network": settings.x402_default_network,
        "facilitator": settings.x402_facilitator_url,
        "wallet_configured": bool(settings.evm_private_key),
        "doctor_ok": bool((report.get("summary") or {}).get("ready")),
        "checks": [
            {
                "id": c.get("id"),
                "passed": c.get("status") == "pass",
                "status": c.get("status"),
                "name": c.get("name"),
                "message": c.get("message"),
            }
            for c in checks
        ],
    }


# Mount MCP Streamable HTTP / SSE transport when available.
if _mcp_http_app is not None:
    app.mount("/mcp", _mcp_http_app)
else:
    try:
        app.mount("/mcp", mcp.sse_app())
    except AttributeError:
        pass

# Mission Control hashed Vite assets (JS/CSS). Must be mounted after API routes.
_mc_assets = _MC_DIST / "assets"
if _mc_assets.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_mc_assets)),
        name="mission-control-assets",
    )