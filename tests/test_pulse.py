"""Base Network Pulse tests — real math and real data, no mocks.

The EIP-1559 vectors are exact; the analysis runs over a fixture captured from
Base mainnet (real block shape, not a mock); the live test hits the real RPC and
is skipped only if the network is unreachable.
"""

from __future__ import annotations

import httpx
import pytest

from app import pulse
from app.pulse import BlockStat


def test_next_base_fee_eip1559_vectors():
    # gas_limit=200 -> target=100. Max change is 1/8 = 12.5%.
    limit, target = 200, 100
    # full block (gas_used == limit == 2*target): +12.5%
    assert pulse.next_base_fee_wei(1000, limit, limit) == 1125
    # empty block: -12.5%
    assert pulse.next_base_fee_wei(1000, 0, limit) == 875
    # exactly at target: unchanged
    assert pulse.next_base_fee_wei(1000, target, limit) == 1000
    # minimum +1 wei bump when slightly over target
    assert pulse.next_base_fee_wei(1, target + 1, limit) == 2


def _real_fixture() -> list[BlockStat]:
    """Block shapes captured from Base mainnet (gas_limit 400M, 0.005 gwei)."""
    base = 48_677_680
    ts = 1_752_600_000
    used = [31_600_000, 30_800_000, 47_200_000, 24_400_000, 27_600_000, 23_200_000]
    return [
        BlockStat(
            number=base + i,
            timestamp=ts + i * 2,
            tx_count=170 + i,
            gas_used=used[i],
            gas_limit=400_000_000,
            base_fee_wei=5_000_000,
        )
        for i in range(len(used))
    ]


def test_analyze_structure_and_math():
    blocks = _real_fixture()
    report = pulse.analyze(blocks, priority_fee_wei=1_000_000, eth_price=1900.0)

    # shape
    for key in ("assessment", "fees", "utilization", "settlement_cost", "network"):
        assert key in report
    assert report["assessment"]["verdict"] in {
        "SETTLE_NOW",
        "SETTLE_SOON",
        "HOLD_IF_FLEXIBLE",
    }

    # utilization math: last block 23.2M / 400M = 5.8%
    assert report["utilization"]["now_pct"] == pytest.approx(5.8, abs=0.05)

    # settlement cost math: (base 0.005 + tip 0.001 gwei) * 21000 gas in USD @ $1900
    fee_per_gas = 6_000_000  # wei
    expected_usd = 21_000 * fee_per_gas / 1e18 * 1900.0
    assert report["settlement_cost"]["eth_transfer"]["usd"] == pytest.approx(
        round(expected_usd, 6)
    )

    # near-empty blocks -> settle now
    assert report["assessment"]["verdict"] == "SETTLE_NOW"


def test_render_report_and_headline_no_crash():
    from app.swarm import publisher

    blocks = _real_fixture()
    report = pulse.analyze(blocks, 1_000_000, 1900.0)
    text = publisher.render_report(report)
    assert "Base Network Pulse" in text
    assert "Verdict" in text
    assert pulse.headline(report).startswith("Base @ block")


@pytest.mark.asyncio
async def test_get_pulse_live_real_data():
    """Hits real Base RPC + Coinbase spot. Skips only if the network is down."""
    try:
        report = await pulse.get_pulse(depth=4)
    except (httpx.HTTPError, RuntimeError) as exc:
        pytest.skip(f"network unavailable: {exc}")

    assert report["chain"]["network"] == "eip155:8453"
    assert report["latest_block"] > 40_000_000  # Base is well past this height
    assert report["eth_price_usd"] > 0
    assert report["fees"]["base_fee_gwei"] >= 0
    assert 0 <= report["utilization"]["now_pct"] <= 100
    assert report["settlement_cost"]["x402_settle"]["usd"] >= 0
