"""Synthesis publisher — turn a live Base Network Pulse into a payable product.

This is the "swap the input" step: instead of composing junk Bazaar feeds, the
archivist synthesizes free, quality Base RPC data into a decision (the Pulse) and
lists it as a real x402-payable composite. Cost basis ~$0 (data is free to read);
the margin is entirely in the synthesis.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app import pulse, x402_services
from app.config import settings
from app.models import BuildSellerRequirementsInput
from app.ops_events import emit_swarm_step
from app.swarm.models import CompositeProduct
from app.swarm.registry import swarm_registry


def parse_price_usdc(price_str: str) -> float:
    return float(price_str.replace("$", "").strip())


def render_report(data: dict[str, Any]) -> str:
    """The digital good a buyer receives: a readable settlement-intelligence brief."""
    a = data["assessment"]
    f = data["fees"]
    u = data["utilization"]
    net = data["network"]
    sc = data["settlement_cost"]
    lines = [
        f"# Base Network Pulse - block {data['latest_block']}",
        f"_{data['generated_at']} · ETH ${data['eth_price_usd']:,.2f}_",
        "",
        f"## Verdict: {a['verdict'].replace('_', ' ')}",
        a["rationale"],
        "",
        f"**Window:** {a['window']}",
        "",
        "## Settlement conditions",
        f"- Base fee: **{f['base_fee_gwei']} gwei** (next block projected "
        f"{f['next_base_fee_gwei']} gwei, {f['next_base_fee_change_pct']:+.1f}%)",
        f"- Priority tip: {f['priority_fee_gwei']} gwei",
        f"- Utilization: **{u['now_pct']}%** now, {u['avg_pct']}% avg, trend "
        f"*{u['trend']}*, {u['headroom_x']}x headroom",
        f"- Block time {net['block_time_s']}s · ~{net['tps_est']} tps",
        "",
        "## Cost to settle right now (USD)",
        f"- ETH transfer: **${sc['eth_transfer']['usd']:.6f}**",
        f"- USDC transfer: **${sc['erc20_usdc_transfer']['usd']:.6f}**",
        f"- x402 settle (EIP-3009): **${sc['x402_settle']['usd']:.6f}**",
        "",
        f"_Source: {data['sources']['rpc']} + Coinbase spot · "
        f"{data['sources']['method']}_",
    ]
    return "\n".join(lines)


async def publish_pulse_product(
    agent_id: str, price_usdc: float | None = None
) -> CompositeProduct:
    """Synthesize a live Pulse and list it as a payable x402 product."""
    data = await pulse.get_pulse()
    price = price_usdc if price_usdc is not None else parse_price_usdc(settings.pulse_price)

    product = CompositeProduct(
        product_id=uuid.uuid4().hex,
        topic=f"Base Network Pulse @ block {data['latest_block']}",
        cost_basis_usdc=0.0,  # quality input data is free to read
        price_usdc=price,
        markup=0.0,
        network=settings.swarm_sell_network,
        sources=[settings.base_rpc_url, settings.eth_price_url],
        report=render_report(data),
        status="draft",
        seller_agent_id=agent_id,
        ltv_cac_projected=0.0,
    )

    # build_seller_requirements does sync facilitator I/O (server.initialize());
    # run it off the event loop so a hung facilitator can't freeze the API.
    requirements = await asyncio.to_thread(
        x402_services.build_seller_requirements,
        BuildSellerRequirementsInput(
            network=settings.swarm_sell_network,
            price=f"${price:.6f}",
            description=f"Base Network Pulse - settlement intelligence @ block {data['latest_block']}",
        ),
    )
    product.seller_requirements = requirements
    product.status = "listed"
    swarm_registry.list_product(product)

    emit_swarm_step(
        run_id=product.product_id,
        role="archivist",
        phase="publishing",
        action="publish_pulse_product",
        detail={
            "product_id": product.product_id,
            "price_usdc": price,
            "verdict": data["assessment"]["verdict"],
            "block": data["latest_block"],
        },
    )
    return product
