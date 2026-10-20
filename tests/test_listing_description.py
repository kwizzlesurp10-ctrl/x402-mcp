"""The served description must not embed data that goes stale.

Discovery catalogs (CDP Bazaar) index the description once, at publish, and
never revisit it — while the listing itself is rebuilt with newer data. Anything
volatile in here is frozen at whatever the catalog first saw and drifts further
every day, so buyers browsing Bazaar read a claim the product no longer meets.
The block height belongs in the report the buyer receives, not in the pitch.
"""

from __future__ import annotations

import base64
import json
import re

import pytest

from app.swarm import publisher

BLOCK = 48915100


@pytest.fixture
def published(monkeypatch):
    """Publish against a fixed Pulse, capturing the description that was built."""
    captured = {}

    async def _fake_pulse():
        return {
            "latest_block": BLOCK,
            "generated_at": "2026-07-21T07:00:00+00:00",
            "eth_price_usd": 3000.0,
            "assessment": {
                "verdict": "settle_now",
                "rationale": "fees are low",
                "window": "next 10 blocks",
            },
            "fees": {
                "base_fee_gwei": 0.01,
                "next_base_fee_gwei": 0.011,
                "next_base_fee_change_pct": 1.0,
                "priority_fee_gwei": 0.001,
            },
            "utilization": {
                "now_pct": 40.0,
                "avg_pct": 38.0,
                "trend": "flat",
                "headroom_x": 2.5,
            },
            "network": {"block_time_s": 2.0, "tps_est": 30},
            "settlement_cost": {
                "eth_transfer": {"usd": 0.001},
                "erc20_usdc_transfer": {"usd": 0.002},
                "x402_settle": {"usd": 0.003},
            },
            "sources": {"rpc": "https://mainnet.base.org", "method": "rpc + spot"},
        }

    def _fake_requirements(params):
        captured["description"] = params.description
        return {"payment_required_header": "hdr", "pay_to": "0xabc"}

    monkeypatch.setattr(publisher.pulse, "get_pulse", _fake_pulse)
    monkeypatch.setattr(
        publisher.x402_services, "build_seller_requirements", _fake_requirements
    )
    return captured


@pytest.mark.asyncio
async def test_description_carries_no_block_height(published) -> None:
    product = await publisher.publish_pulse_product("agent-1", product_id="p1")

    description = published["description"]
    assert str(BLOCK) not in description
    # No bare block-height-looking number at all — the point is that nothing in
    # here can go stale, not merely that today's block is absent.
    assert not re.search(r"\b\d{6,}\b", description)
    assert product.seller_requirements["payment_required_header"] == "hdr"


@pytest.mark.asyncio
async def test_description_still_says_what_is_sold(published) -> None:
    """Dropping the block must not cost the terms Bazaar retrieval matches on."""
    await publisher.publish_pulse_product("agent-1", product_id="p1")

    description = published["description"].lower()
    for term in ("base", "mainnet", "x402", "usdc", "gas", "block", "eth"):
        assert term in description, f"lost retrieval term: {term}"


@pytest.mark.asyncio
async def test_the_block_still_reaches_the_buyer(published) -> None:
    """It belongs in the report — that is the thing being paid for."""
    product = await publisher.publish_pulse_product("agent-1", product_id="p1")

    assert str(BLOCK) in product.report
    assert str(BLOCK) in product.topic
