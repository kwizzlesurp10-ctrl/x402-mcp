"""Fund-First Settle Ticket — USDC to payTo before any paid payload.

GET /pay/ticket
  Unpaid → 402 + Bazaar-discoverable PAYMENT-REQUIRED (never 422)
  Paid   → verify/settle, then a signed one-use grant. No ArcGIS/pack compute.

GET /pay/ticket/sample
  Free control: ticket shape + pointers. Never settles.

The grant is a capability for one existing access-barrier job
(POST /tasks/us-rental-diligence). Expensive pack compute stays on that route.

Seller stays keyless: grant MAC uses operator_token or a process-local secret,
never EVM_PRIVATE_KEY.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings

log = logging.getLogger("x402")

PRODUCT_ID = "fund-first-ticket"
SERVICE_NAME = "Fund-First Settle Ticket"  # 24 chars, <=32
SERVICE_TAGS = ["fund-first", "ticket", "usdc", "diligence", "x402"]
UNLOCKS = "POST /tasks/us-rental-diligence"
GRANT_HEADER = "X-FUND-FIRST-TICKET"
# Base mainnet native USDC — the only asset this SKU sells on eip155:8453.
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
# Circle USDC on Base Sepolia — local/dev only; never mixed into mainnet inventory.
SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

RESOURCE_DESCRIPTION = (
    "Fund-first settle ticket: USDC settles to payTo before any paid payload. "
    "Paid GET returns a one-use grant that unlocks POST /tasks/us-rental-diligence. "
    "Not a free-RPC synthesis. Free sample: GET /pay/ticket/sample."
)

DISCOVERY_INPUT_EXAMPLE: dict[str, Any] = {}

DISCOVERY_OUTPUT_EXAMPLE: dict[str, Any] = {
    "ticket_id": "example-ticket-id",
    "product_id": PRODUCT_ID,
    "pay_to": "0xAB745e5F576667037696e78ba7dA28E193E4423D",
    "network": "eip155:8453",
    "asset": BASE_USDC,
    "amount_usdc": 0.05,
    "tx": "0xabc",
    "payer": "0xbuyer",
    "settled_at": "2026-08-27T00:00:00+00:00",
    "grant": "example-grant",
}

router = APIRouter(tags=["pay"])

_PROCESS_SECRET = secrets.token_bytes(32)
_lock = threading.Lock()
_issued: dict[str, dict[str, Any]] = {}
_consumed: set[str] = set()


def reset_grants_for_tests() -> None:
    with _lock:
        _issued.clear()
        _consumed.clear()


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


def price_string() -> str:
    return settings.fund_first_ticket_price


def resource_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}/pay/ticket"


def sample_url() -> str:
    return f"{resource_url()}/sample"


def city_sample_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}/us/sea/property-check/sample"


def diligence_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}/tasks/us-rental-diligence"


def _hmac_secret() -> bytes:
    token = settings.operator_token
    if token:
        return token.encode("utf-8")
    return _PROCESS_SECRET


def _mac(ticket_id: str) -> str:
    msg = f"{ticket_id}|{PRODUCT_ID}|{UNLOCKS}".encode()
    return hmac.new(_hmac_secret(), msg, hashlib.sha256).hexdigest()[:32]


def build_payment_required_header() -> str:
    from app import challenge_cache
    from app.models import BuildSellerRequirementsInput
    from app.x402_services import build_seller_requirements

    network = sell_network()
    price = price_string()
    res = resource_url()
    tags = list(SERVICE_TAGS)
    fp = challenge_cache.fingerprint(
        network=network,
        price=price,
        resource=res,
        discoverable=settings.bazaar_discoverable,
        description=RESOURCE_DESCRIPTION,
        input_example=DISCOVERY_INPUT_EXAMPLE,
        output_example=DISCOVERY_OUTPUT_EXAMPLE,
        service_name=SERVICE_NAME,
        service_tags=tags,
        method="GET",
    )

    def _build() -> str:
        return build_seller_requirements(
            BuildSellerRequirementsInput(
                network=network,
                price=price,
                description=RESOURCE_DESCRIPTION,
                resource_url=res,
                mime_type="application/json",
                discovery_method="GET",
                discovery_input_example=DISCOVERY_INPUT_EXAMPLE,
                discovery_output_example=DISCOVERY_OUTPUT_EXAMPLE,
                service_name=SERVICE_NAME,
                service_tags=tags,
            )
        )["payment_required_header"]

    return challenge_cache.get_or_build(PRODUCT_ID, fp, _build)


async def verify_and_settle(payment_signature: str, payment_required: str) -> dict:
    from app.models import VerifyPaymentInput
    from app.x402_services import _verify_and_settle_payment

    return await _verify_and_settle_payment(
        VerifyPaymentInput(
            payment_signature=payment_signature,
            payment_required=payment_required,
        )
    )


def issue_settled_ticket(settlement: dict[str, Any]) -> dict[str, Any]:
    """Mint the paid product. Call only after facilitator success=true."""
    ticket_id = uuid.uuid4().hex
    grant = f"{ticket_id}.{_mac(ticket_id)}"
    network = str(settlement.get("network") or sell_network())
    tx = settlement.get("transaction") or settlement.get("txHash")
    ticket = {
        "ticket_id": ticket_id,
        "product_id": PRODUCT_ID,
        "pay_to": settings.x402_pay_to_address,
        "network": network,
        "asset": sell_asset(network),
        "amount_usdc": amount_usdc(),
        "tx": str(tx) if tx else None,
        "payer": settlement.get("payer"),
        "settled_at": datetime.now(UTC).isoformat(),
        "grant": grant,
        "unlocks": UNLOCKS,
        "city_sample_url": city_sample_url(),
        "diligence_url": diligence_url(),
    }
    with _lock:
        _issued[ticket_id] = {
            "grant": grant,
            "unlocks": UNLOCKS,
            "payer": ticket["payer"],
            "tx": ticket["tx"],
        }
    return ticket


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
        if ticket_id not in _issued:
            return None
        if ticket_id in _consumed:
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


def _seller_misconfigured() -> JSONResponse | None:
    if not settings.x402_pay_to_address:
        return JSONResponse(
            status_code=503,
            content={
                "error": "seller_not_configured",
                "detail": "X402_PAY_TO_ADDRESS unset",
            },
        )
    return None


def _challenge_or_503() -> tuple[str | None, JSONResponse | None]:
    try:
        return build_payment_required_header(), None
    except Exception:  # noqa: BLE001
        log.warning("fund-first-ticket: cannot build challenge", exc_info=True)
        return None, JSONResponse(
            status_code=503,
            headers={"Retry-After": "30"},
            content={"error": "challenge_unavailable", "detail": "retry shortly"},
        )


def _402_body(payment_required: str) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        headers={"PAYMENT-REQUIRED": payment_required},
        content={
            "error": "payment_required",
            "resource": resource_url(),
            "product_id": PRODUCT_ID,
            "price": price_string(),
            "network": sell_network(),
            "asset": sell_asset(),
            "pay_to": settings.x402_pay_to_address,
            "description": RESOURCE_DESCRIPTION,
            "sample_url": sample_url(),
            "unlocks": UNLOCKS,
            "how_to_pay": (
                "Retry GET /pay/ticket with PAYMENT-SIGNATURE (x402 v2 exact). "
                "Requirements are in the PAYMENT-REQUIRED response header. "
                f"Free control: GET {sample_url()}. "
                f"Grant header on the bound job: {GRANT_HEADER}."
            ),
        },
    )


@router.get("/pay/ticket/sample")
async def fund_first_ticket_sample() -> JSONResponse:
    """Free ticket shape + pointers. Never settles. Never runs the pack."""
    return JSONResponse(
        content={
            "sample": True,
            "product_id": PRODUCT_ID,
            "price": price_string(),
            "network": sell_network(),
            "asset": sell_asset(),
            "pay_to": settings.x402_pay_to_address,
            "paid_url": resource_url(),
            "city_sample_url": city_sample_url(),
            "diligence_url": diligence_url(),
            "unlocks": UNLOCKS,
            "grant_header": GRANT_HEADER,
            "note": (
                "Unpaid GET /pay/ticket returns 402. Paid GET returns a one-use "
                "grant after USDC settles to payTo. Present the grant as "
                f"{GRANT_HEADER} on {UNLOCKS}. Pack compute stays on that route."
            ),
        }
    )


@router.get("/pay/ticket")
async def fund_first_ticket_get(request: Request) -> JSONResponse:
    """Paid fund-first ticket. Payload computed only after settle succeeds."""
    t0 = time.monotonic()
    bad = _seller_misconfigured()
    if bad:
        return bad
    payment_required, err = _challenge_or_503()
    if err:
        return err
    assert payment_required is not None

    signature = request.headers.get("PAYMENT-SIGNATURE")
    if not signature:
        from app import demand

        if not demand.is_self_traffic(request.headers):
            demand.record_challenge(PRODUCT_ID, request.headers.get("user-agent"))
        return _402_body(payment_required)

    result = await verify_and_settle(signature, payment_required)
    settlement = result.get("settlement") or {}
    settled = bool(result.get("is_valid") and result.get("payment_settled"))
    if settled and settlement.get("success") is False:
        settled = False
    if not settled:
        return JSONResponse(
            status_code=402,
            headers={"PAYMENT-REQUIRED": payment_required},
            content={
                "error": "payment_rejected",
                "invalid_reason": result.get("invalid_reason"),
                "settlement_error": result.get("settlement_error"),
            },
        )

    ticket = issue_settled_ticket(settlement)
    tx = ticket.get("tx")
    try:
        from app.swarm import ledger_writer

        ledger_writer.record_revenue(
            agent_id=PRODUCT_ID,
            amount_usdc=amount_usdc(),
            network=str(ticket["network"]),
            product_id=PRODUCT_ID,
            tx=str(tx) if tx else None,
            payer=ticket.get("payer"),
        )
    except Exception:  # noqa: BLE001
        log.warning("fund-first-ticket revenue ledger write failed", exc_info=True)

    latency = round((time.monotonic() - t0) * 1000)
    log.info(
        "fund-first-ticket settled",
        extra={"status_code": 200, "latency_ms": latency},
    )
    receipt = base64.b64encode(json.dumps(settlement, default=str).encode()).decode()
    return JSONResponse(content=ticket, headers={"PAYMENT-RESPONSE": receipt})
