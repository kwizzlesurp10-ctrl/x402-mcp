"""Synthesis publisher — turn a live Base Network Pulse into a payable product.

This is the "swap the input" step: instead of composing junk Bazaar feeds, the
archivist synthesizes free, quality Base RPC data into a decision (the Pulse) and
lists it as a real x402-payable composite. Cost basis ~$0 (data is free to read);
the margin is entirely in the synthesis.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from app import pulse, x402_services
from app.config import settings
from app.models import BuildSellerRequirementsInput
from app.ops_events import emit_swarm_step
from app.swarm.models import CompositeProduct, purchase_discovery_metadata
from app.swarm.registry import swarm_registry

log = logging.getLogger("x402")

# Stable seller identity for the pinned listing, so revenue rows stay attributable
# across restarts instead of picking up a fresh uuid on every boot.
_PINNED_SELLER_AGENT_ID = "pinned-pulse-seller"


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


async def restore_pinned_listing() -> CompositeProduct | None:
    """Make sure PINNED_PULSE_PRODUCT_ID is listed and sellable, republishing if not.

    Called at startup. On an ephemeral host (Render free) a restart wipes
    ledger/products.json, so the registry comes back empty and the purchase URL
    sitting in the CDP Bazaar catalog answers 404 — the listing is indexed but
    dead, and buyers who discovered it get nothing. Republishing onto the same id
    rebuilds a fresh Pulse behind the same URL.

    Returns None when pinning is disabled or the republish failed; never raises,
    because a listing that can't be rebuilt must not stop the server from
    booting (the rest of the API, /health included, still works).
    """
    pinned = settings.pinned_pulse_product_id.strip()
    if not pinned:
        return None

    existing = swarm_registry.get_product(pinned)
    if existing and (existing.seller_requirements or {}).get("payment_required_header"):
        log.info("pinned listing %s survived the restart; not republishing", pinned)
        return existing

    try:
        product = await publish_pulse_product(
            agent_id=_PINNED_SELLER_AGENT_ID, product_id=pinned
        )
    except Exception:  # noqa: BLE001 — boot must not fail on a listing rebuild
        log.exception("pinned listing %s could not be republished", pinned)
        return None

    log.info(
        "pinned listing %s republished at $%.2f on %s",
        pinned,
        product.price_usdc,
        product.network,
    )
    return product


async def publish_pulse_product(
    agent_id: str,
    price_usdc: float | None = None,
    product_id: str | None = None,
) -> CompositeProduct:
    """Synthesize a live Pulse and list it as a payable x402 product.

    Pass `product_id` to republish onto an existing id — the purchase URL embeds
    it, so reusing the id is what keeps an already-cataloged listing resolvable
    across a restart. The id has to be set before the seller requirements are
    built, since the discovery metadata carries the URL derived from it.
    """
    data = await pulse.get_pulse()
    price = price_usdc if price_usdc is not None else parse_price_usdc(settings.pulse_price)

    product = CompositeProduct(
        product_id=product_id or uuid.uuid4().hex,
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
    # Discovery metadata makes the served 402 Bazaar-catalogable on settle.
    requirements = await asyncio.to_thread(
        x402_services.build_seller_requirements,
        BuildSellerRequirementsInput(
            network=settings.swarm_sell_network,
            price=f"${price:.6f}",
            description=(
                "Base mainnet settlement intelligence (Base Network Pulse) for "
                "pricing x402 / USDC agent micropayments: live network economics "
                f"at block {data['latest_block']} — block time, base fee and "
                "priority fee (gas), ETH price, and the USD cost to settle an ETH "
                "transfer and an ERC-20/USDC transfer. GET, no inputs; returns "
                "JSON computed from Base RPC + spot price, no API key required."
            ),
            **purchase_discovery_metadata(product, settings.public_base_url),
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
