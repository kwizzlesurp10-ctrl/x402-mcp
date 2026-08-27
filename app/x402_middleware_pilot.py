"""Standalone pilot of the x402 SDK's own FastAPI payment middleware.

Every other paid route in this repo (Pulse, /base/tx-decision,
/mn/property-check) hand-rolls its own challenge/verify/settle path —
mostly because each needed something the generic middleware doesn't give
you for free (challenge caching through a flaky facilitator, demand
instrumentation that excludes self-traffic, a payer address captured
*before* settlement for the ledger). Rewriting those was evaluated and
declined: for this codebase, migrating trades ~40 lines of tested, working
code for a similar amount of hook glue, plus a real regression (payment
gated before request validation, since the SDK gates at the ASGI layer
before the route handler runs).

This module is the other half of that decision: prove the SDK's own
`x402.http.middleware.fastapi.PaymentMiddlewareASGI` actually works end to
end against this server's real facilitator config, as its own isolated
section, so the pattern is available for whatever paid endpoint turns out
to need it — without touching any current route.

`GET /pilot/ping` is the protocol proof: nominally priced, not cataloged,
not a product. `GET /base/finality-check` (app/finality_check.py) is the
first real one — the first paid product in this repo gated by the generic
middleware instead of a hand-rolled challenge/verify/settle path.

These two routes used to earn real money with no ledger row, because the
gap above was read as "the SDK has no post-settlement hook". It does:
`x402ResourceServer.on_after_settle` (x402 2.14.0, x402/server.py:137),
whose hook runs only once the facilitator has returned a settled
`SettleResponse` (x402/server_base.py:1301-1310). `_record_settled_revenue`
below hangs off that, so revenue is mirrored into `ledger_writer` /
`/demand` / the dashboard on the same terms as the hand-rolled products —
after settlement succeeded, never from the pre-settlement payload, which is
exactly the inflated-revenue bug the 2026-07-25 payer-classification work
was written to prevent.

The funnel's other half is counted in `_InstrumentedPaymentMiddleware`: the
SDK answers the 402 itself at the ASGI layer, so there is no handler to
count the challenge from, and without it `/demand` would report sales
against zero views and no conversion at all.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query
from starlette.applications import Starlette

from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter()

# Both halves of the funnel key off this map. The value MUST be used verbatim
# as BOTH the demand `resource_key` and the revenue `product_id`: app/demand.py
# joins challenges to revenue rows on that string (demand.py:246-255), and a
# mismatch reports the product as having made zero sales.
PRODUCT_IDS = {
    "/base/finality-check": "base-finality-check",
    "/pilot/ping": "pilot-ping",
    "/pay/ticket": "fund-first-ticket",
}


def _configured_price(product_id: str) -> str | None:
    """The listed price for a product, used only as a last-resort amount."""
    if product_id == "base-finality-check":
        return settings.finality_check_price
    if product_id == "pilot-ping":
        return settings.middleware_pilot_price
    if product_id == "fund-first-ticket":
        return settings.fund_first_ticket_price
    return None


def _settled_amount_usdc(result: Any, requirements: Any, product_id: str) -> float | None:
    """What this settlement actually earned, in USDC.

    Precedence mirrors the buy side (x402_services.pay_and_fetch): the
    facilitator's own settled amount first (the only figure that reflects a
    partial settlement), then the requirement the buyer paid against, then the
    listed price. Never invents a number.
    """
    from app import x402_services

    network = getattr(result, "network", None) or getattr(requirements, "network", None)
    asset = getattr(requirements, "asset", None)

    amount = x402_services.atomic_to_units(getattr(result, "amount", None), network, asset)
    if amount is not None:
        return amount

    get_amount = getattr(requirements, "get_amount", None)
    raw = get_amount() if callable(get_amount) else getattr(requirements, "amount", None)
    amount = x402_services.atomic_to_units(raw, network, asset)
    if amount is not None:
        return amount

    price = _configured_price(product_id)
    if price:
        from app.swarm.publisher import parse_price_usdc

        return parse_price_usdc(price)
    return None


def _record_settled_revenue(ctx: Any) -> None:
    """`on_after_settle` hook for this module's own x402ResourceServer.

    The SDK also runs after-settle hooks for a result *recovered* by an
    on_settle_failure hook, so `result.success is True` is re-checked here
    rather than assumed from the phase — same standard as the hand-rolled
    products (`is_valid` and `payment_settled`, app/main.py:709).

    Never raises. The SDK does not wrap resource-server after-settle hooks, so
    an exception here escapes `process_settlement` into the middleware's
    `except Exception: return 402` (x402/http/middleware/fastapi.py:377-378) —
    a ledger row failing would hand a paying, settled buyer a 402 instead of
    the product they just paid for.
    """
    try:
        result = getattr(ctx, "result", None)
        if getattr(result, "success", None) is not True:
            return

        # Which of the two gated routes settled. HTTPTransportContext.request is
        # the HTTPRequestContext the middleware built (x402/http/types.py:75-91);
        # PaymentRequirements v2 carries no resource URL, so this is the only
        # reliable mapping back to a product.
        request = getattr(getattr(ctx, "transport_context", None), "request", None)
        product_id = PRODUCT_IDS.get(str(getattr(request, "path", "") or ""))
        if not product_id:
            return

        requirements = getattr(ctx, "requirements", None)
        amount = _settled_amount_usdc(result, requirements, product_id)
        if amount is None:
            log.warning("%s: settled but no amount recoverable; not recorded", product_id)
            return

        tx = getattr(result, "transaction", None)
        from app.swarm import ledger_writer

        network = str(
            getattr(result, "network", None)
            or getattr(requirements, "network", None)
            or settings.x402_default_network
        )
        payer = getattr(result, "payer", None)
        ledger_writer.record_revenue(
            agent_id=product_id,
            amount_usdc=amount,
            network=network,
            product_id=product_id,
            tx=str(tx) if tx else None,
            payer=payer,
        )
        if product_id == "fund-first-ticket":
            from app import fund_first

            fund_first.capture_settlement(
                tx=str(tx) if tx else None,
                payer=payer,
                network=network,
                amount_usdc=amount,
                asset=getattr(requirements, "asset", None),
            )
    except Exception:  # noqa: BLE001 — a ledger row is never worth a lost sale
        log.warning("middleware pilot: revenue ledger write failed", exc_info=True)


def record_402_challenge(request: Any, status_code: int) -> None:
    """Count a 402 served for one of the two gated routes. Never raises.

    Only the *unsigned* request counts, matching the hand-rolled products
    (app/main.py:683-686): a 402 handed back after a signature was presented is
    a failed payment, not a fresh look at the price, and counting it would
    depress the conversion of exactly the product that is converting.
    """
    try:
        if status_code != 402:
            return
        product_id = PRODUCT_IDS.get(request.url.path)
        if not product_id:
            return
        headers = request.headers
        if headers.get("PAYMENT-SIGNATURE") or headers.get("X-PAYMENT"):
            return

        from app import demand

        if demand.is_self_traffic(headers):
            return
        demand.record_challenge(product_id, headers.get("user-agent"))
    except Exception:  # noqa: BLE001 — a counter must never break a request
        log.warning("middleware pilot: failed to record a challenge", exc_info=True)


@router.get("/pilot/ping")
async def pilot_ping() -> dict:
    """The protected handler. By the time this runs, the SDK middleware has
    already verified and settled payment — no challenge/verify/settle code
    here at all, which is the actual point of the pilot."""
    return {"ok": True, "pattern": "x402 SDK FastAPI middleware pilot"}


@router.get("/base/finality-check")
async def base_finality_check(
    tx: str = Query(
        ...,
        pattern=r"^0x[0-9a-fA-F]{64}$",
        description="Base mainnet transaction hash to check",
    ),
) -> dict:
    """The protected handler for the real product. FastAPI's own query
    validation runs here, inside `call_next` — a malformed `tx` produces a
    422 the middleware sees as a handler failure and does not settle for
    (see `PaymentMiddlewareASGI`'s `response.status_code >= 400` check), so
    the "validate before charge" property is preserved despite payment
    gating happening at the ASGI layer."""
    from app.finality_check import check_finality

    return await check_finality(tx)


def instrumented_middleware_class() -> type:
    """`PaymentMiddlewareASGI` plus this repo's top-of-funnel instrumentation.

    Built lazily so importing this module never pulls in the x402 SDK, which
    `register`'s no-pay-to-address early return depends on.
    """
    from x402.http.middleware import PaymentMiddlewareASGI

    class _InstrumentedPaymentMiddleware(PaymentMiddlewareASGI):
        async def dispatch(self, request, call_next):  # type: ignore[override]
            response = await super().dispatch(request, call_next)
            record_402_challenge(request, response.status_code)
            return response

    return _InstrumentedPaymentMiddleware


def register(app: Starlette) -> None:
    """Wire the pilot middleware onto `app`, additively.

    Only requests to the two routes below are gated — every other route
    takes one cheap regex-match-and-pass-through per request
    (`x402HTTPResourceServer.requires_payment`) and is otherwise untouched.
    A no-op (with a log line) if X402_PAY_TO_ADDRESS isn't configured, same
    posture as the seller-only public deployment for every other product.
    """
    if not settings.x402_pay_to_address:
        import logging

        logging.getLogger(__name__).info(
            "x402_middleware_pilot: X402_PAY_TO_ADDRESS unset, not registering"
        )
        return

    from x402.http.types import PaymentOption, RouteConfig

    from app import finality_check, fund_first
    from app.x402_services import (
        _build_discovery_extension,
        _resource_server,
        resolve_revenue_network,
    )

    # This server instance is exclusive to the two routes below, so the hook
    # cannot fire for any other product's settlement.
    server = _resource_server(settings.x402_default_network)
    server.on_after_settle(_record_settled_revenue)

    finality_extensions = None
    if settings.bazaar_discoverable:
        finality_extensions = _build_discovery_extension(
            "GET",
            finality_check.DISCOVERY_INPUT_EXAMPLE,
            finality_check.DISCOVERY_OUTPUT_EXAMPLE,
        )

    tags = [t.strip()[:32] for t in settings.bazaar_service_tags.split(",") if t.strip()][:5]

    fund_first_extensions = None
    if settings.bazaar_discoverable:
        fund_first_extensions = _build_discovery_extension(
            "GET",
            fund_first.DISCOVERY_INPUT_EXAMPLE,
            fund_first.DISCOVERY_OUTPUT_EXAMPLE,
        )

    ticket_network = resolve_revenue_network()

    routes = {
        "GET /pilot/ping": RouteConfig(
            accepts=PaymentOption(
                scheme="exact",
                pay_to=settings.x402_pay_to_address,
                price=settings.middleware_pilot_price,
                network=settings.x402_default_network,
            ),
            description=(
                "x402 SDK middleware pilot endpoint — not a catalog product, "
                "exists to prove the generic FastAPI payment middleware "
                "against this server's real facilitator config."
            ),
            mime_type="application/json",
        ),
        "GET /base/finality-check": RouteConfig(
            accepts=PaymentOption(
                scheme="exact",
                pay_to=settings.x402_pay_to_address,
                price=settings.finality_check_price,
                network=settings.x402_default_network,
            ),
            resource=finality_check.resource_url(),
            description=finality_check.RESOURCE_DESCRIPTION,
            mime_type="application/json",
            service_name=settings.bazaar_service_name.strip()[:32] or None,
            tags=tags or None,
            extensions=finality_extensions,
        ),
        "GET /pay/ticket": RouteConfig(
            accepts=PaymentOption(
                scheme="exact",
                pay_to=settings.x402_pay_to_address,
                price=settings.fund_first_ticket_price,
                network=ticket_network,
            ),
            resource=fund_first.resource_url(),
            description=fund_first.RESOURCE_DESCRIPTION,
            mime_type="application/json",
            service_name=fund_first.SERVICE_NAME,
            tags=list(fund_first.SERVICE_TAGS),
            extensions=fund_first_extensions,
        ),
    }

    app.include_router(router)
    app.include_router(fund_first.paid_router)
    app.add_middleware(
        instrumented_middleware_class(), routes=routes, server=server
    )
