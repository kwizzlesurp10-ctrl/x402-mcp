"""FastAPI application: HTTP transport, manifest, health, MCP SSE mount."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.commerce import quota_store
from app.config import settings
from app.dashboard import DASHBOARD_HTML
from app.manifest import build_mcp_manifest
from app.mcp_server import mcp

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
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "x402-micropayments-mcp",
        "x402_facilitator": settings.x402_facilitator_url,
        "wallet_configured": bool(settings.evm_private_key),
    }


@app.get("/.well-known/mcp")
async def well_known_mcp() -> dict:
    return build_mcp_manifest()


@app.get("/quota/{agent_id}")
async def quota_status(agent_id: str) -> dict:
    """Debug endpoint: inspect quota without consuming a call."""
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


# Mount MCP Streamable HTTP / SSE transport when available.
if _mcp_http_app is not None:
    app.mount("/mcp", _mcp_http_app)
else:
    try:
        app.mount("/mcp", mcp.sse_app())
    except AttributeError:
        pass