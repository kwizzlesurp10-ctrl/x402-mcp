"""Public discovery CORS: directory crawlers and browser probes on paid/free catalog routes.

Does not apply to operator dashboards, wallet, ledger, or mutation APIs.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_DISCOVERY_EXPOSE = "PAYMENT-REQUIRED,PAYMENT-RESPONSE"

# Prefix allowlist — fail closed for everything else (wallet, /swarm/run, etc.).
_DISCOVERY_PREFIXES = (
    "/.well-known/",
    "/openapi.json",
    "/llms.txt",
    "/robots.txt",
    "/us/cities",
    "/mn/property-check",
    "/us/",
    "/base/tx-decision",
    "/base/finality-check",
    "/agent/property-due-diligence",
    "/tasks/us-rental-diligence",
    "/x402/policy-check",
    "/pulse",
    "/swarm/products/",
)

_DISCOVERY_EXACT = (
    "/openapi.json",
    "/llms.txt",
    "/robots.txt",
    "/us/cities",
    "/pulse",
    "/mn/property-check",
    "/base/tx-decision",
    "/base/finality-check",
    "/agent/property-due-diligence",
    "/tasks/us-rental-diligence",
    "/x402/policy-check",
)


def is_public_discovery_path(path: str) -> bool:
    if path in _DISCOVERY_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in _DISCOVERY_PREFIXES)


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": (
            "Accept, Content-Type, PAYMENT-SIGNATURE, X-PAYMENT, X-Agent-Id"
        ),
        "Access-Control-Expose-Headers": _DISCOVERY_EXPOSE,
        "Vary": "Origin",
    }


class DiscoveryCorsMiddleware(BaseHTTPMiddleware):
    """OPTIONS 204 + ACAO * on catalog routes so x402scan/Smithery read 402 headers."""

    async def dispatch(self, request: Request, call_next):
        if not is_public_discovery_path(request.url.path):
            return await call_next(request)

        if request.method == "OPTIONS":
            return Response(status_code=204, headers=_cors_headers())

        response = await call_next(request)
        headers = _cors_headers()
        for key, value in headers.items():
            if key == "Access-Control-Expose-Headers":
                existing = response.headers.get("Access-Control-Expose-Headers", "")
                merged = {p.strip() for p in (existing + "," + value).split(",") if p.strip()}
                response.headers[key] = ",".join(sorted(merged))
            else:
                response.headers.setdefault(key, value)
        return response
