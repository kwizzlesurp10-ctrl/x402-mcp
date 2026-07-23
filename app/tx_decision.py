"""Base tx-decision product: the loop-resident call, paid over x402.

The full Pulse ($0.05) is a briefing — something read once. This endpoint is the
repositioned version of the same intelligence: a compact, per-transaction answer
to "should I submit this Base transaction now, and at what fee?" that a bot can
afford to call every time it queues a tx. Measured market data says that shape
is where x402 demand actually lives: the winners earn 90-140 calls per payer
because they sit inside an agent's runtime loop, not on its reading list.

Same data honesty rules as app/pulse.py: everything is computed from live Base
RPC blocks and a spot price. Where the future is unknowable (when fees will
drop) the response says "re-check in N seconds", never a prediction dressed as
a fact.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app import pulse
from app.config import settings
from app.pulse import (
    GAS_ERC20_TRANSFER,
    GAS_ETH_TRANSFER,
    GAS_X402_SETTLE,
    WEI_PER_GWEI,
)

# Named gas presets so a bot can say what it is sending instead of guessing
# a gas number. "usdc" covers any ERC-20 transfer; custom integers also work.
GAS_PRESETS = {
    "eth": GAS_ETH_TRANSFER,
    "usdc": GAS_ERC20_TRANSFER,
    "erc20": GAS_ERC20_TRANSFER,
    "x402": GAS_X402_SETTLE,
}
URGENCIES = ("now", "soon", "flexible")

# A per-transaction endpoint cannot pay ~13 sequential RPC round trips per call
# (pulse.fetch_blocks walks the blocks one by one). Base blocks land every ~2s,
# so a snapshot this old is still the current fee picture; the response carries
# as_of_block and data_age_s so the caller can judge for itself.
_CACHE_TTL_S = 4.0
_cache: dict[str, Any] = {"at": 0.0, "report": None}
_cache_lock = asyncio.Lock()


async def _fresh_pulse() -> dict[str, Any]:
    async with _cache_lock:
        age = time.monotonic() - _cache["at"]
        if _cache["report"] is not None and age < _CACHE_TTL_S:
            return _cache["report"]
        report = await pulse.get_pulse()
        _cache["at"] = time.monotonic()
        _cache["report"] = report
        return report


def decide(report: dict[str, Any], gas: int, urgency: str) -> dict[str, Any]:
    """Turn a Pulse report into one transaction's submit/wait decision."""
    fees = report["fees"]
    assessment = report["assessment"]
    utilization = report["utilization"]
    block_time_s = report["network"]["block_time_s"] or 2.0
    eth_price = report["eth_price_usd"]

    base_fee_gwei = fees["base_fee_gwei"]
    priority_gwei = fees["priority_fee_gwei"]

    # Standard EIP-1559 wallet sizing: max_fee = 2*base + tip rides out several
    # consecutive full blocks without the tx getting stuck; the expected cost
    # uses the CURRENT base + tip, because the surplus max_fee is never burned.
    max_fee_gwei = round(2 * base_fee_gwei + priority_gwei, 6)
    effective_gwei = base_fee_gwei + priority_gwei
    cost_eth = gas * effective_gwei / 1e9
    cost_usd = cost_eth * eth_price

    verdict = assessment["verdict"]
    if urgency == "now":
        # The caller has already decided to send; our job is the fee, not doubt.
        submit = True
    elif urgency == "soon":
        submit = verdict in ("SETTLE_NOW", "SETTLE_SOON")
    else:  # flexible
        submit = verdict == "SETTLE_NOW"

    recheck_in_s = None
    if not submit:
        # No one can predict when base fee eases; the honest advice is when a
        # re-check becomes informative — a handful of blocks, sooner if the
        # trend is already falling.
        blocks_to_wait = 3 if utilization["trend"] == "falling" else 6
        recheck_in_s = int(blocks_to_wait * block_time_s)

    return {
        "submit": submit,
        "urgency": urgency,
        "verdict": verdict,
        "why": assessment["rationale"],
        "fee": {
            "max_fee_per_gas_gwei": max_fee_gwei,
            "max_priority_fee_per_gas_gwei": priority_gwei,
            "current_base_fee_gwei": base_fee_gwei,
            "next_base_fee_gwei": fees["next_base_fee_gwei"],
        },
        "estimated_cost": {
            "gas": gas,
            "eth": round(cost_eth, 12),
            "usd": round(cost_usd, 6),
        },
        "recheck_in_s": recheck_in_s,
        "as_of_block": report["latest_block"],
        "as_of": report["generated_at"],
        "chain": report["chain"]["network"],
    }


async def advise(gas: int, urgency: str) -> dict[str, Any]:
    report = await _fresh_pulse()
    return decide(report, gas, urgency)


# ---- x402 seller gate (mirrors app/mn_compliance.py) -------------------------


def resource_url() -> str:
    return f"{settings.public_base_url}/base/tx-decision"


# Written as the query an agent would type, not a brand phrase — the discovery
# catalog ranks on full-text + semantic match over this string.
RESOURCE_DESCRIPTION = (
    "Should I submit this Base transaction now, and at what fee? One call "
    "returns submit-or-wait, max fee per gas and priority fee in gwei "
    "(EIP-1559), and the estimated cost in USD for an ETH transfer, USDC "
    "ERC-20 transfer, or x402 settlement on Base mainnet. Live gas price and "
    "congestion from Base RPC blocks, no API key. For bots that queue "
    "transactions: call before every send."
)

DISCOVERY_INPUT_EXAMPLE: dict[str, Any] = {"gas": "usdc", "urgency": "flexible"}

DISCOVERY_OUTPUT_EXAMPLE: dict[str, Any] = {
    "submit": True,
    "verdict": "SETTLE_NOW",
    "fee": {
        "max_fee_per_gas_gwei": 0.012,
        "max_priority_fee_per_gas_gwei": 0.001,
        "current_base_fee_gwei": 0.0055,
    },
    "estimated_cost": {"gas": 55000, "usd": 0.0011},
    "recheck_in_s": None,
    "as_of_block": 48941850,
}


def build_payment_required_header() -> str:
    """Base64 x402 v2 PAYMENT-REQUIRED header for this resource.

    Cached per (network, price, resource): the header is static, and building it
    hits the CDP facilitator, which 502s. Serving a cached header keeps selling
    through a facilitator outage instead of 500-ing every unpaid request.
    """
    from app import challenge_cache
    from app.models import BuildSellerRequirementsInput
    from app.x402_services import build_seller_requirements

    network = settings.x402_default_network
    price = settings.tx_decision_price
    fp = f"{network}|{price}|{resource_url()}|disc={settings.bazaar_discoverable}"

    def _build() -> str:
        return build_seller_requirements(
            BuildSellerRequirementsInput(
                network=network,
                price=price,
                description=RESOURCE_DESCRIPTION,
                resource_url=resource_url(),
                mime_type="application/json",
                discovery_method="GET",
                discovery_input_example=DISCOVERY_INPUT_EXAMPLE,
                discovery_output_example=DISCOVERY_OUTPUT_EXAMPLE,
            )
        )["payment_required_header"]

    return challenge_cache.get_or_build("base-tx-decision", fp, _build)


async def verify_and_settle(payment_signature: str, payment_required: str) -> dict:
    from app.models import VerifyPaymentInput
    from app.x402_services import _verify_and_settle_payment

    return await _verify_and_settle_payment(
        VerifyPaymentInput(
            payment_signature=payment_signature,
            payment_required=payment_required,
        )
    )
