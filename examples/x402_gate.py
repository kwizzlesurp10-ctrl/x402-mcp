"""Minimal FastAPI x402 402-gate — charge USDC to access an endpoint.

    pip install fastapi uvicorn "x402>=2"
    export X402_PAY_TO=0xYourReceiveAddress
    uvicorn examples.x402_gate:app --port 8000

Flow: unpaid GET -> HTTP 402 + PAYMENT-REQUIRED challenge; the caller's x402
client signs and retries with PAYMENT-SIGNATURE; we verify AND settle, then
deliver the content plus a PAYMENT-RESPONSE settlement header.

Testnet (Base Sepolia, default) settles for free via x402.org. For Base
MAINNET set X402_NETWORK=eip155:8453 and point at the CDP facilitator with
auth (see the note at the bottom) — the free facilitator only settles testnet.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from x402 import ResourceConfig, x402ResourceServer
from x402.http import (
    FacilitatorConfig,
    HTTPFacilitatorClient,
    decode_payment_required_header,
    decode_payment_signature_header,
    encode_payment_required_header,
    encode_payment_response_header,
)
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.schemas import PaymentRequired

PAY_TO = os.environ["X402_PAY_TO"]                     # your receive address
NETWORK = os.environ.get("X402_NETWORK", "eip155:84532")   # Base Sepolia
FACILITATOR = os.environ.get("X402_FACILITATOR", "https://x402.org/facilitator")
PRICE = os.environ.get("X402_PRICE", "$0.01")


def _resource_server() -> x402ResourceServer:
    server = x402ResourceServer(HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR)))
    server.register("eip155:*", ExactEvmServerScheme())   # only `exact` is registered
    server.initialize()
    return server


_server = _resource_server()
_requirements = _server.build_payment_requirements(
    ResourceConfig(
        scheme="exact",
        network=NETWORK,
        pay_to=PAY_TO,
        price=PRICE,
        description="Paid API access",
    )
)
# Encode the 402 challenge once; serve it verbatim on PAYMENT-REQUIRED.
CHALLENGE = encode_payment_required_header(
    PaymentRequired(x402_version=2, accepts=list(_requirements), error="Payment required")
)

app = FastAPI()


@app.get("/paid")
async def paid(request: Request):
    signature = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("X-PAYMENT")
    if not signature:
        return JSONResponse(
            status_code=402,
            content={"error": "payment_required", "price": PRICE, "pay_to": PAY_TO},
            headers={
                "PAYMENT-REQUIRED": CHALLENGE,
                "Access-Control-Expose-Headers": "PAYMENT-REQUIRED,PAYMENT-RESPONSE",
            },
        )

    payload = decode_payment_signature_header(signature)
    requirements = decode_payment_required_header(CHALLENGE).accepts[0]

    verify = await _server.verify_payment(payload, requirements)
    if not verify.is_valid:
        return JSONResponse(
            status_code=402,
            content={"error": "invalid_payment", "reason": verify.invalid_reason},
        )

    settle = await _server.settle_payment(payload, requirements)
    if not settle.success:  # verify != settle — only deliver once funds actually move
        return JSONResponse(
            status_code=402,
            content={"error": "not_settled", "reason": settle.error_reason},
        )

    response = JSONResponse(content={"data": "🔓 your paid content here"})
    response.headers["PAYMENT-RESPONSE"] = encode_payment_response_header(settle)
    return response


# ── Base mainnet note ──────────────────────────────────────────────────────
# The free facilitator only settles Base Sepolia. For mainnet (eip155:8453),
# build a CDP-authenticated facilitator instead:
#
#   from app.cdp_auth import build_cdp_create_headers
#   create_headers = build_cdp_create_headers(
#       os.environ["CDP_API_KEY_ID"], os.environ["CDP_API_KEY_SECRET"],
#       "https://api.cdp.coinbase.com/platform/v2/x402")
#   facilitator = HTTPFacilitatorClient(
#       {"url": "https://api.cdp.coinbase.com/platform/v2/x402",
#        "create_headers": create_headers})
