"""Fund-First Settle Ticket — USDC to payTo before any paid payload.

GET /pay/ticket        paid; registered only when X402_PAY_TO_ADDRESS is set
                       (PaymentMiddlewareASGI + on_after_settle).
GET /pay/ticket/sample free control; never settles.

Handler body for the paid route runs only after middleware settle success.
Grant is a one-use capability for POST /tasks/us-rental-diligence.
Seller stays keyless: grant MAC uses operator_token or a process-local secret.
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import logging
import secrets
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings

log = logging.getLogger("x402")

PRODUCT_ID = "fund-first-ticket"
PAID_PATH = "/pay/ticket"
SAMPLE_PATH = "/pay/ticket/sample"
SERVICE_NAME = "Fund-First Settle Ticket"  # 24 chars, <=32
SERVICE_TAGS = ["fund-first", "ticket", "usdc", "diligence", "x402"]
UNLOCKS = "POST /tasks/us-rental-diligence"
GRANT_HEADER = "X-FUND-FIRST-TICKET"
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

RESOURCE_DESCRIPTION = (
    "Fund-first settle ticket: USDC settles to payTo before any paid payload. "
    "Paid GET returns a one-use grant for POST /tasks/us-rental-diligence. "
    "Not a free-RPC synthesis. Free sample: GET /pay/ticket/sample."
)

DISCOVERY_INPUT_EXAMPLE: dict[str, Any] = {}

DISCOVERY_OUTPUT_EXAMPLE: dict[str, Any] = {
    "ok": True,
    "product_id": PRODUCT_ID,
    "pay_to": "0xAB745e5F576667037696e78ba7dA28E193E4423D",
    "network": "eip155:8453",
    "asset": BASE_USDC,
    "amount_usdc": 0.05,
    "tx": "0xabc",
    "payer": "0xbuyer",
    "ticket_id": "example-ticket-id",
    "grant": "example-grant",
    "unlocks": UNLOCKS,
    "settled_at": "2026-08-27T00:00:00+00:00",
}

sample_router = APIRouter(tags=["pay"])
paid_router = APIRouter(tags=["pay"])

_PROCESS_SECRET = secrets.token_bytes(32)
_lock = threading.Lock()
_issued: dict[str, dict[str, Any]] = {}
_consumed: set[str] = set()
_settle_ctx: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "fund_first_settle", default=None
)


def reset_grants_for_tests() -> None:
    with _lock:
        _issued.clear()
        _consumed.clear()
    _settle_ctx.set(None)


def sell_network() -> str:
    from app.x402_services import resolve_revenue_network

    return resolve_revenue_network()


def sell_asset(network: str | None = None) -> str:
    net = network or sell_network()
    if net == "eip155:8453":
        return BASE_USDC
    return SEPOLIA_USDC


def amount_usdc() -> float:
    from app.swarm.publisher import parse_price_usdc

    return parse_price_usdc(settings.fund_first_ticket_price)


def resource_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}{PAID_PATH}"


def sample_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}{SAMPLE_PATH}"


def _hmac_secret() -> bytes:
    token = settings.operator_token
    if token:
        return token.encode("utf-8")
    return _PROCESS_SECRET


def _mac(ticket_id: str) -> str:
    msg = f"{ticket_id}|{PRODUCT_ID}|{UNLOCKS}".encode()
    return hmac.new(_hmac_secret(), msg, hashlib.sha256).hexdigest()[:32]


def capture_settlement(
    *,
    tx: str | None,
    payer: str | None,
    network: str,
    amount_usdc: float,
    asset: str | None,
) -> None:
    """Called from on_after_settle after success=true. Never raises."""
    try:
        _settle_ctx.set(
            {
                "tx": tx,
                "payer": payer,
                "network": network,
                "amount_usdc": amount_usdc,
                "asset": asset or sell_asset(network),
            }
        )
    except Exception:  # noqa: BLE001
        log.warning("fund-first: capture_settlement failed", exc_info=True)


def peek_grant(grant: str) -> dict[str, Any] | None:
    raw = (grant or "").strip()
    if "." not in raw:
        return None
    ticket_id, mac = raw.split(".", 1)
    if not ticket_id or not mac:
        return None
    expected = _mac(ticket_id)
    if not hmac.compare_digest(mac, expected):
        return None
    with _lock:
        if ticket_id not in _issued or ticket_id in _consumed:
            return None
        return {"ticket_id": ticket_id, **_issued[ticket_id]}


def consume_grant(grant: str) -> dict[str, Any] | None:
    peeked = peek_grant(grant)
    if not peeked:
        return None
    with _lock:
        tid = peeked["ticket_id"]
        if tid in _consumed or tid not in _issued:
            return None
        _consumed.add(tid)
        return peeked


def issue_settled_ticket(
    *,
    pay_to: str,
    network: str,
    asset: str,
    amount: float,
    tx: str | None,
    payer: str | None,
) -> dict[str, Any]:
    ticket_id = uuid.uuid4().hex
    grant = f"{ticket_id}.{_mac(ticket_id)}"
    ticket = {
        "ok": True,
        "product_id": PRODUCT_ID,
        "pay_to": pay_to,
        "network": network,
        "asset": asset,
        "amount_usdc": amount,
        "tx": tx,
        "payer": payer,
        "ticket_id": ticket_id,
        "grant": grant,
        "unlocks": UNLOCKS,
        "settled_at": datetime.now(UTC).isoformat(),
    }
    with _lock:
        _issued[ticket_id] = {
            "grant": grant,
            "unlocks": UNLOCKS,
            "payer": payer,
            "tx": tx,
        }
    return ticket


@sample_router.get(SAMPLE_PATH)
async def fund_first_sample() -> JSONResponse:
    """Free terms. Never settles."""
    pay_to = settings.x402_pay_to_address
    network = sell_network()
    body: dict[str, Any] = {
        "sample": True,
        "product_id": PRODUCT_ID,
        "price": settings.fund_first_ticket_price,
        "network": network,
        "asset": sell_asset(network),
        "payTo_field": "payTo",
        "paid_url": resource_url(),
        "unlocks": UNLOCKS,
        "grant_header": GRANT_HEADER,
        "how_to_pay": (
            "Retry GET /pay/ticket with PAYMENT-SIGNATURE (x402 v2 exact). "
            "Read PAYMENT-REQUIRED on the 402. Never settle on /sample."
        ),
    }
    if not pay_to:
        body["seller_unconfigured"] = True
    else:
        body["pay_to"] = pay_to
        body["seller_unconfigured"] = False
    return JSONResponse(content=body)


@paid_router.get(PAID_PATH)
async def fund_first_paid() -> JSONResponse:
    """Runs only after PaymentMiddlewareASGI has settled. No pack compute."""
    ctx = _settle_ctx.get()
    pay_to = settings.x402_pay_to_address
    if not pay_to:
        return JSONResponse(
            status_code=503,
            content={
                "error": "seller_not_configured",
                "detail": "X402_PAY_TO_ADDRESS unset",
            },
        )
    if not ctx or ctx.get("amount_usdc") is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": "settlement_context_missing",
                "detail": "handler ran without on_after_settle capture",
            },
        )
    network = str(ctx.get("network") or sell_network())
    ticket = issue_settled_ticket(
        pay_to=pay_to,
        network=network,
        asset=str(ctx.get("asset") or sell_asset(network)),
        amount=float(ctx["amount_usdc"]),
        tx=ctx.get("tx"),
        payer=ctx.get("payer"),
    )
    return JSONResponse(content=ticket)
