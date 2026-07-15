"""Swarm orchestrator: run the buy → compose → list cycle, and settle sales.

Greenfield state machine (the repo has no orchestration layer). Each phase
delegates to a role in app.swarm.roles, records an audit step, and emits an SSE
event. Money moves for real when EVM_PRIVATE_KEY (buy) and X402_PAY_TO_ADDRESS
(sell) are configured; otherwise the failing phase surfaces a clear error.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app import x402_services
from app.config import settings
from app.models import VerifyPaymentInput
from app.ops_events import emit_swarm_step
from app.swarm import ledger_writer, policy as policy_mod, roles
from app.swarm.models import SwarmRun
from app.swarm.registry import swarm_registry


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def run_swarm_research(
    topic: str,
    agent_id: str,
    max_price_usdc: float | None = None,
) -> dict[str, Any]:
    """Execute one full Agency cycle for a research topic and return the run."""
    run = SwarmRun(
        run_id=uuid.uuid4().hex,
        topic=topic,
        agent_id=agent_id,
        status="scouting",
        started_ts=_now(),
    )
    swarm_registry.add_run(run)
    policy = policy_mod.load_policy()
    cap = (
        max_price_usdc
        if max_price_usdc is not None
        else policy.max_price_per_call_usdc
    )

    try:
        # SCOUT
        candidates = await roles.scout(run, topic, cap)
        run.steps.append({"role": "scout", "candidates": len(candidates)})
        if not candidates:
            raise RuntimeError(
                "scout found no upstream services. Set SWARM_UPSTREAM_URLS to "
                "known x402 endpoints or check CDP discovery connectivity."
            )

        # WARDEN
        run.status = "reviewing"
        approved = roles.warden_review(
            run, candidates, policy, settings.swarm_max_upstream_calls
        )
        run.steps.append(
            {"role": "warden", "approved": len(approved), "vetoed": len(run.vetoes)}
        )
        if not approved:
            raise RuntimeError(
                "warden vetoed every candidate (policy caps / unknown price). "
                "No purchase made."
            )

        # TREASURER
        run.status = "buying"
        purchases = await roles.treasurer_buy(run, approved)
        run.steps.append({"role": "treasurer", "purchased": len(purchases)})
        if not purchases:
            raise RuntimeError("treasurer completed no purchases.")

        # ARCHIVIST
        run.status = "composing"
        network = purchases[0].network
        product = roles.archivist_compose(
            run,
            purchases,
            topic,
            settings.swarm_markup,
            settings.swarm_min_price_usdc,
            network,
        )
        run.steps.append({"role": "archivist", "product_id": product.product_id})

        # SOVEREIGN
        from app.swarm import sovereign

        run.status = "optimizing"
        product = sovereign.optimize_pricing(
            run,
            product,
            settings.swarm_target_ltv_cac,
            settings.swarm_min_margin_ratio,
            settings.swarm_min_price_usdc,
        )

        # MERCHANT
        run.status = "listing"
        product = roles.merchant_list(run, product, settings.swarm_sell_network)
        swarm_registry.list_product(product)
        run.steps.append({"role": "merchant", "status": "listed"})

        run.status = "listed"
    except Exception as exc:  # noqa: BLE001 — surface the failure on the run object
        run.status = "failed"
        run.error = str(exc)
        emit_swarm_step(
            run_id=run.run_id,
            role="orchestrator",
            phase="failed",
            action="swarm_error",
            detail={"error": str(exc)},
        )
    finally:
        run.finished_ts = _now()

    return run.to_dict()


async def settle_composite_sale(
    product_id: str,
    payment_signature: str,
    payment_required: str,
    buyer_agent_id: str,
) -> dict[str, Any]:
    """Verify + settle a buyer's payment for a listed composite; record revenue."""
    product = swarm_registry.get_product(product_id)
    if product is None:
        raise ValueError(f"unknown product_id: {product_id}")

    payment = await x402_services._verify_and_settle_payment(
        VerifyPaymentInput(
            payment_signature=payment_signature,
            payment_required=payment_required,
        )
    )
    if not payment["is_valid"]:
        raise ValueError(
            f"composite sale payment invalid: {payment.get('invalid_reason', 'unknown')}"
        )

    settlement = payment.get("settlement") or {}
    tx = None
    if isinstance(settlement, dict):
        tx = (
            settlement.get("transaction")
            or settlement.get("txHash")
            or settlement.get("transactionHash")
        )

    product.status = "sold"
    product.revenue_usdc = round(product.revenue_usdc + product.price_usdc, 6)
    ledger_writer.record_revenue(
        agent_id=buyer_agent_id,
        amount_usdc=product.price_usdc,
        network=product.network,
        product_id=product.product_id,
        tx=str(tx) if tx else None,
        settled=payment["payment_settled"],
    )
    # Attribute realized revenue back to the sources that fed the composite.
    sources = product.sources or []
    if sources:
        per_source = product.price_usdc / len(sources)
        for source in sources:
            swarm_registry.record_source_revenue(source, per_source)
    emit_swarm_step(
        run_id=product.product_id,
        role="merchant",
        phase="selling",
        action="settle_composite_sale",
        detail={
            "product_id": product.product_id,
            "revenue_usdc": product.price_usdc,
            "margin_usdc": product.margin_usdc,
            "settled": payment["payment_settled"],
        },
    )
    return {
        "sold": True,
        "product_id": product.product_id,
        "revenue_usdc": product.price_usdc,
        "cost_basis_usdc": product.cost_basis_usdc,
        "margin_usdc": product.margin_usdc,
        "payment_settled": payment["payment_settled"],
        "report": product.report,
        "verification": payment,
    }
