"""Sovereign role: profit optimizer / revenue orchestrator.

Runs after the archivist composes the priced composite and before the merchant
lists it, tightening price to hit the target LTV:CAC and margin floor. Also
provides read-only portfolio economics (spend, revenue, LTV:CAC, per-source
profit scores) for mission-control revenue intelligence.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.ledger_io import read_ledger_rows
from app.ops_events import emit_swarm_step
from app.swarm.models import CompositeProduct, SwarmRun
from app.swarm.registry import swarm_registry


def optimize_pricing(
    run: SwarmRun,
    product: CompositeProduct,
    target_ltv_cac: float,
    min_margin_ratio: float,
    min_price: float,
) -> CompositeProduct:
    """Re-price the composite to hit target LTV:CAC and the margin floor.

    Never lowers below the archivist's price; records per-source cost intel so
    the revenue report can score upstream sources by realized profit.
    """
    cost = product.cost_basis_usdc
    price = max(
        product.price_usdc,
        round(cost * target_ltv_cac, 6),
        min_price,
    )
    product.price_usdc = price
    product.markup = round(price / cost, 4) if cost > 0 else product.markup
    product.ltv_cac_projected = round(price / cost, 4) if cost > 0 else 0.0

    # Enforce the margin floor: (price - cost) / price >= min_margin_ratio.
    if cost > 0 and (price - cost) / price < min_margin_ratio:
        price = round(cost / (1 - min_margin_ratio), 6)
        product.price_usdc = price
        product.markup = round(price / cost, 4)
        product.ltv_cac_projected = round(price / cost, 4)

    # Record per-source cost intel (split cost basis evenly across sources).
    sources = product.sources or []
    if sources:
        per_source = cost / len(sources)
        for source in sources:
            swarm_registry.record_source_buy(source, per_source)

    emit_swarm_step(
        run_id=run.run_id,
        role="sovereign",
        phase="optimizing",
        action="optimize_pricing",
        detail={
            "product_id": product.product_id,
            "price_usdc": product.price_usdc,
            "ltv_cac_projected": product.ltv_cac_projected,
            "target_ltv_cac": target_ltv_cac,
        },
    )
    run.steps.append(
        {"role": "sovereign", "ltv_cac_projected": product.ltv_cac_projected}
    )
    return product


def build_revenue_report() -> dict[str, Any]:
    """Read-only portfolio economics for the swarm (spend, revenue, LTV:CAC)."""
    spend_rows = read_ledger_rows("spend")
    revenue_rows = read_ledger_rows("revenue")

    total_spend = round(sum(r.get("amount_usdc", 0.0) for r in spend_rows), 6)
    total_revenue = round(sum(r.get("amount_usdc", 0.0) for r in revenue_rows), 6)
    realized_margin = round(total_revenue - total_spend, 6)
    ltv_cac = round(total_revenue / total_spend, 4) if total_spend else None

    products = swarm_registry.products()
    listed_count = sum(1 for p in products if p["status"] == "listed")
    sold_count = sum(1 for p in products if p["status"] == "sold")

    product_rows: list[dict[str, Any]] = []
    for p in products:
        cost = p["cost_basis_usdc"]
        price = p["price_usdc"]
        ltv_cac_projected = round(price / cost, 4) if cost > 0 else 0.0
        product_rows.append(
            {
                "product_id": p["product_id"],
                "topic": p["topic"],
                "cost_basis_usdc": round(cost, 6),
                "price_usdc": round(price, 6),
                "margin_usdc": round(p["margin_usdc"], 6),
                "status": p["status"],
                "ltv_cac_projected": ltv_cac_projected,
            }
        )

    target = settings.swarm_target_ltv_cac
    recommendations: list[str] = []
    if ltv_cac is not None and ltv_cac < target:
        recommendations.append(
            f"portfolio LTV:CAC {ltv_cac} below target {target}: "
            "raise markup or cut upstream spend"
        )
    if listed_count:
        recommendations.append(
            f"{listed_count} composites listed but unsold: awaiting buyers"
        )
    if not total_spend:
        recommendations.append("no runs yet")

    return {
        "total_spend_usdc": total_spend,
        "total_revenue_usdc": total_revenue,
        "realized_margin_usdc": realized_margin,
        "ltv_cac": ltv_cac,
        "target_ltv_cac": target,
        "listed_count": listed_count,
        "sold_count": sold_count,
        "products": product_rows,
        "source_scores": swarm_registry.source_scores(),
        "recommendations": recommendations,
    }
