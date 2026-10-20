"""Sovereign role: profit optimizer / revenue orchestrator.

Runs after the archivist composes the priced composite and before the merchant
lists it, tightening price to hit the target LTV:CAC and margin floor. Also
provides read-only swarm composite economics (spend, composite sales, LTV:CAC,
per-source profit scores). First-party storefront sales are reported under
`storefront`, not mixed into `total_revenue_usdc`.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.ledger_io import (
    classify_operator_settle,
    operator_wallet_set,
    read_ledger_rows,
)
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
    # Clamp the margin floor into [0, 1) so a misconfigured ratio can't divide
    # by zero or produce a negative price below.
    min_margin_ratio = min(max(min_margin_ratio, 0.0), 0.99)

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

    # Record per-source cost intel using each purchase's REAL settled amount
    # (not an even split), so source profit scores are accurate.
    for purchase in run.purchases:
        swarm_registry.record_source_buy(purchase.url, purchase.amount_usdc)

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


def _empty_revenue_bucket() -> dict[str, Any]:
    return {
        "revenue_usdc": 0.0,
        "settled_sales": 0,
        "external_usdc": 0.0,
        "operator_usdc": 0.0,
        "unknown_usdc": 0.0,
        "external_sales": 0,
        "operator_sales": 0,
        "unknown_sales": 0,
    }


def _credit_bucket(bucket: dict[str, Any], amount: float, is_operator: bool | None) -> None:
    bucket["revenue_usdc"] += amount
    bucket["settled_sales"] += 1
    if is_operator is True:
        bucket["operator_usdc"] += amount
        bucket["operator_sales"] += 1
    elif is_operator is False:
        bucket["external_usdc"] += amount
        bucket["external_sales"] += 1
    else:
        bucket["unknown_usdc"] += amount
        bucket["unknown_sales"] += 1


def _round_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    return {
        "revenue_usdc": round(bucket["revenue_usdc"], 6),
        "settled_sales": int(bucket["settled_sales"]),
        "external_usdc": round(bucket["external_usdc"], 6),
        "operator_usdc": round(bucket["operator_usdc"], 6),
        "unknown_usdc": round(bucket["unknown_usdc"], 6),
        "external_sales": int(bucket["external_sales"]),
        "operator_sales": int(bucket["operator_sales"]),
        "unknown_sales": int(bucket["unknown_sales"]),
    }


def is_swarm_revenue_row(row: dict[str, Any], swarm_ids: set[str]) -> bool:
    """Attribute a ledger row to the swarm portfolio, not the HTTP storefront.

    First-party SKUs (city checks, pulse-1, diligence, tx-decision, …) write
    `run_id=None` and a product_id that is never a CompositeProduct. Composite
    sales always set `run_id`, and current listings also match `swarm_ids`.
    Either signal is enough so a pruned composite still counts as swarm
    revenue instead of silently becoming "storefront".
    """
    pid = str(row.get("product_id") or "")
    if pid in swarm_ids:
        return True
    return bool(row.get("run_id"))


def build_revenue_report() -> dict[str, Any]:
    """Read-only swarm portfolio economics (spend, composite sales, LTV:CAC).

    `total_revenue_usdc` / `sold_count` / `products` are swarm composites
    only. The full settled ledger (city checks, Pulse HTTP, diligence, …)
    lives under `storefront` so a first-party sale cannot look like a
    composite that sold — issue #527.
    """
    # limit=None: aggregate the entire ledger; settled-only so unsettled
    # attempts never inflate spend/revenue/margin.
    spend_rows = read_ledger_rows("spend", limit=None)
    revenue_rows = read_ledger_rows("revenue", limit=None)

    total_spend = round(
        sum(r.get("amount_usdc", 0.0) for r in spend_rows if r.get("settled", True)), 6
    )

    products = swarm_registry.products()
    swarm_ids = {p["product_id"] for p in products}

    try:
        operator_wallets = operator_wallet_set()
    except Exception:  # never raise into a request path
        operator_wallets = set()

    storefront = _empty_revenue_bucket()
    swarm = _empty_revenue_bucket()
    by_product: dict[str, dict[str, float]] = {}

    for row in revenue_rows:
        if not row.get("settled", True):
            continue
        amount = float(row.get("amount_usdc") or 0.0)
        pid = str(row.get("product_id") or "unknown")
        stats = by_product.setdefault(pid, {"revenue_usdc": 0.0, "sales": 0.0})
        stats["revenue_usdc"] += amount
        stats["sales"] += 1
        try:
            is_operator = classify_operator_settle(row, operator_wallets)
        except Exception:  # a malformed row is unknown, never external
            is_operator = None
        _credit_bucket(storefront, amount, is_operator)
        if is_swarm_revenue_row(row, swarm_ids):
            _credit_bucket(swarm, amount, is_operator)

    storefront_out = _round_bucket(storefront)
    swarm_out = _round_bucket(swarm)
    first_party_usdc = round(
        storefront_out["revenue_usdc"] - swarm_out["revenue_usdc"], 6
    )
    storefront_out["first_party_revenue_usdc"] = first_party_usdc
    storefront_out["swarm_revenue_usdc"] = swarm_out["revenue_usdc"]

    total_revenue = swarm_out["revenue_usdc"]
    realized_margin = round(total_revenue - total_spend, 6)
    ltv_cac = round(total_revenue / total_spend, 4) if total_spend else None

    product_rows: list[dict[str, Any]] = []
    sold_count = 0
    listed_count = 0
    listed_unsold_count = 0
    for p in products:
        cost = p["cost_basis_usdc"]
        price = p["price_usdc"]
        ltv_cac_projected = round(price / cost, 4) if cost > 0 else 0.0
        stats = by_product.get(p["product_id"], {"revenue_usdc": 0.0, "sales": 0.0})
        ledger_revenue = round(float(stats["revenue_usdc"]), 6)
        sales_settled = int(stats["sales"])
        status = p["status"]
        has_sales = status == "sold" or sales_settled > 0
        if has_sales:
            sold_count += 1
        if status == "listed":
            listed_count += 1
            if sales_settled == 0:
                listed_unsold_count += 1
        product_rows.append(
            {
                "product_id": p["product_id"],
                "topic": p["topic"],
                "cost_basis_usdc": round(cost, 6),
                "price_usdc": round(price, 6),
                "margin_usdc": round(p["margin_usdc"], 6),
                "status": status,
                "ltv_cac_projected": ltv_cac_projected,
                "revenue_usdc": ledger_revenue,
                "sales_settled": sales_settled,
            }
        )

    target = settings.swarm_target_ltv_cac
    recommendations: list[str] = []
    if ltv_cac is not None and ltv_cac < target:
        recommendations.append(
            f"swarm LTV:CAC {ltv_cac} below target {target}: "
            "raise markup or cut upstream spend"
        )
    if listed_unsold_count:
        noun = "composite" if listed_unsold_count == 1 else "composites"
        recommendations.append(
            f"{listed_unsold_count} {noun} listed with no settled sales"
        )
    if not total_spend:
        recommendations.append("no runs yet")
    if first_party_usdc and not total_revenue:
        recommendations.append(
            f"storefront has {first_party_usdc} USDC settled on first-party SKUs; "
            "swarm composites have not sold — see storefront.first_party_revenue_usdc"
        )

    return {
        "scope": "swarm_composites",
        "note": (
            "total_revenue_usdc, sold_count, and products are swarm composites "
            "only. storefront.revenue_usdc is the full settled ledger (city "
            "checks, pulse-1, diligence, tx-decision, …). Operator self-settles "
            "are not external demand; see storefront.external_usdc."
        ),
        "total_spend_usdc": total_spend,
        "total_revenue_usdc": total_revenue,
        "realized_margin_usdc": realized_margin,
        "ltv_cac": ltv_cac,
        "target_ltv_cac": target,
        "listed_count": listed_count,
        "listed_unsold_count": listed_unsold_count,
        "sold_count": sold_count,
        "products": product_rows,
        "source_scores": swarm_registry.source_scores(),
        "recommendations": recommendations,
        "storefront": storefront_out,
    }
