"""Base Network Pulse — live settlement-conditions intelligence for Base mainnet.

Real data only, no mocks:
- block data from the Base JSON-RPC (`eth_getBlockByNumber`),
- ETH/USD from Coinbase's public spot API,
- next-block base fee via the EIP-1559 algorithm
  (BASE_FEE_MAX_CHANGE_DENOMINATOR=8, ELASTICITY_MULTIPLIER=2, gas_target=gas_limit/2;
  ethereum/EIPs EIPS/eip-1559.md).

The product this powers: a synthesized "should I settle on Base right now?" call —
turning raw chain numbers into a decision an x402 / stablecoin-payments operator
will pay for.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings

WEI_PER_GWEI = 1_000_000_000
WEI_PER_ETH = 1_000_000_000_000_000_000

# EIP-1559 constants (identical on the OP-stack / Base).
BASE_FEE_MAX_CHANGE_DENOMINATOR = 8
ELASTICITY_MULTIPLIER = 2

# Representative gas costs for the payments an x402 operator actually cares about.
GAS_ETH_TRANSFER = 21_000
GAS_ERC20_TRANSFER = 55_000  # typical USDC ERC-20 transfer
GAS_X402_SETTLE = 100_000  # EIP-3009 transferWithAuthorization (facilitator settle)


@dataclass
class BlockStat:
    number: int
    timestamp: int
    tx_count: int
    gas_used: int
    gas_limit: int
    base_fee_wei: int

    @property
    def utilization(self) -> float:
        return self.gas_used / self.gas_limit if self.gas_limit else 0.0


async def _rpc(client: httpx.AsyncClient, method: str, params: list[Any]) -> Any:
    resp = await client.post(
        settings.base_rpc_url,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"RPC {method} error: {data['error']}")
    return data["result"]


def _block_stat(raw: dict) -> BlockStat:
    return BlockStat(
        number=int(raw["number"], 16),
        timestamp=int(raw["timestamp"], 16),
        tx_count=len(raw["transactions"]),
        gas_used=int(raw["gasUsed"], 16),
        gas_limit=int(raw["gasLimit"], 16),
        base_fee_wei=int(raw.get("baseFeePerGas", "0x0"), 16),
    )


async def fetch_blocks(client: httpx.AsyncClient, depth: int) -> list[BlockStat]:
    """Fetch the latest `depth` blocks (oldest first)."""
    latest = int(await _rpc(client, "eth_blockNumber", []), 16)
    blocks: list[BlockStat] = []
    for n in range(latest - depth + 1, latest + 1):
        raw = await _rpc(client, "eth_getBlockByNumber", [hex(n), False])
        blocks.append(_block_stat(raw))
    return blocks


async def fetch_priority_fee_wei(client: httpx.AsyncClient) -> int:
    try:
        return int(await _rpc(client, "eth_maxPriorityFeePerGas", []), 16)
    except Exception:  # noqa: BLE001 — node may not implement it; treat tip as ~0
        return 0


async def fetch_eth_price_usd(client: httpx.AsyncClient) -> float:
    resp = await client.get(settings.eth_price_url)
    resp.raise_for_status()
    return float(resp.json()["data"]["amount"])


def next_base_fee_wei(parent_base_fee: int, gas_used: int, gas_limit: int) -> int:
    """EIP-1559 next-block base fee from the parent block."""
    gas_target = gas_limit // ELASTICITY_MULTIPLIER
    if gas_used == gas_target or gas_target == 0:
        return parent_base_fee
    if gas_used > gas_target:
        delta = max(
            parent_base_fee
            * (gas_used - gas_target)
            // gas_target
            // BASE_FEE_MAX_CHANGE_DENOMINATOR,
            1,
        )
        return parent_base_fee + delta
    delta = (
        parent_base_fee
        * (gas_target - gas_used)
        // gas_target
        // BASE_FEE_MAX_CHANGE_DENOMINATOR
    )
    return parent_base_fee - delta


def _trend(values: list[float]) -> str:
    """Least-squares slope sign over the series -> rising/falling/flat."""
    n = len(values)
    if n < 3:
        return "flat"
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return "flat"
    slope = sum((xs[i] - mx) * (values[i] - my) for i in range(n)) / denom
    mean = my or 1e-12
    # normalise slope to the mean level; ignore sub-2%/block drift as flat.
    rel = slope / abs(mean)
    if rel > 0.02:
        return "rising"
    if rel < -0.02:
        return "falling"
    return "flat"


def _congestion(util_pct: float) -> str:
    if util_pct < 20:
        return "abundant"
    if util_pct < 50:
        return "comfortable"
    if util_pct < 75:
        return "elevated"
    if util_pct < 90:
        return "busy"
    return "congested"


def _settlement_cost(gas: int, fee_per_gas_wei: int, eth_price: float) -> dict[str, Any]:
    total_wei = gas * fee_per_gas_wei
    eth = total_wei / WEI_PER_ETH
    return {
        "gas": gas,
        "fee_gwei": round(total_wei / WEI_PER_GWEI, 6),
        "eth": round(eth, 12),
        "usd": round(eth * eth_price, 6),
    }


def analyze(
    blocks: list[BlockStat], priority_fee_wei: int, eth_price: float
) -> dict[str, Any]:
    """Synthesize the settlement-conditions call from real block data."""
    latest = blocks[-1]
    util_series = [b.utilization * 100 for b in blocks]
    util_now = util_series[-1]
    util_avg = sum(util_series) / len(util_series)
    util_trend = _trend(util_series)

    times = [blocks[i].timestamp - blocks[i - 1].timestamp for i in range(1, len(blocks))]
    block_time = sum(times) / len(times) if times else 0.0
    avg_txs = sum(b.tx_count for b in blocks) / len(blocks)
    tps = avg_txs / block_time if block_time else 0.0

    base_fee_wei = latest.base_fee_wei
    next_bf = next_base_fee_wei(base_fee_wei, latest.gas_used, latest.gas_limit)
    fee_per_gas = base_fee_wei + priority_fee_wei  # what a tx actually pays

    congestion = _congestion(util_now)
    headroom = round(latest.gas_limit / latest.gas_used, 1) if latest.gas_used else None

    # Decision synthesis — thresholds on real conditions.
    base_fee_gwei = base_fee_wei / WEI_PER_GWEI
    cheap = base_fee_gwei < 0.05 and util_now < 50
    tightening = util_trend == "rising" and util_now > 55
    if congestion in ("abundant", "comfortable") and not tightening:
        verdict = "SETTLE_NOW"
        rationale = (
            f"Blockspace is {util_now:.1f}% full at {base_fee_gwei:.4f} gwei - "
            f"settlement is at or near the floor with ~{headroom}x headroom. "
            "No congestion premium; a stablecoin transfer settles for a fraction of a cent."
        )
    elif tightening or congestion == "elevated":
        verdict = "SETTLE_SOON"
        rationale = (
            f"Utilization is {util_now:.1f}% and {util_trend}; the cheap window is "
            "tightening. Settle time-sensitive payments now before base fee steps up."
        )
    else:
        verdict = "HOLD_IF_FLEXIBLE"
        rationale = (
            f"Blockspace is {congestion} ({util_now:.1f}% full) at "
            f"{base_fee_gwei:.4f} gwei; non-urgent settlement can wait for the next dip."
        )

    if util_trend == "rising":
        window = "closing - utilization rising; expect base fee to step up"
    elif util_trend == "falling":
        window = "opening - utilization falling; base fee easing"
    else:
        window = "stable - utilization flat over the sampled window"

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "chain": {"name": "Base mainnet", "network": "eip155:8453"},
        "latest_block": latest.number,
        "eth_price_usd": round(eth_price, 2),
        "network": {
            "block_time_s": round(block_time, 2),
            "tps_est": round(tps, 1),
            "gas_limit": latest.gas_limit,
            "gas_target": latest.gas_limit // ELASTICITY_MULTIPLIER,
        },
        "fees": {
            "base_fee_gwei": round(base_fee_gwei, 6),
            "priority_fee_gwei": round(priority_fee_wei / WEI_PER_GWEI, 6),
            "next_base_fee_gwei": round(next_bf / WEI_PER_GWEI, 6),
            "next_base_fee_change_pct": round(
                (next_bf - base_fee_wei) / base_fee_wei * 100, 2
            )
            if base_fee_wei
            else 0.0,
        },
        "utilization": {
            "now_pct": round(util_now, 1),
            "avg_pct": round(util_avg, 1),
            "trend": util_trend,
            "headroom_x": headroom,
            "series_pct": [round(u, 1) for u in util_series],
        },
        "settlement_cost": {
            "eth_transfer": _settlement_cost(GAS_ETH_TRANSFER, fee_per_gas, eth_price),
            "erc20_usdc_transfer": _settlement_cost(
                GAS_ERC20_TRANSFER, fee_per_gas, eth_price
            ),
            "x402_settle": _settlement_cost(GAS_X402_SETTLE, fee_per_gas, eth_price),
        },
        "assessment": {
            "congestion": congestion,
            "verdict": verdict,
            "rationale": rationale,
            "window": window,
        },
        "sources": {
            "rpc": settings.base_rpc_url,
            "price": settings.eth_price_url,
            "method": "EIP-1559 (ethereum/EIPs eip-1559.md); measured, not modeled",
        },
    }


async def get_pulse(depth: int | None = None) -> dict[str, Any]:
    """Fetch live data and return the synthesized Base Network Pulse report."""
    n = depth or settings.pulse_depth
    async with httpx.AsyncClient(timeout=20.0) as client:
        blocks = await fetch_blocks(client, n)
        priority = await fetch_priority_fee_wei(client)
        eth_price = await fetch_eth_price_usd(client)
    return analyze(blocks, priority, eth_price)


def headline(report: dict[str, Any]) -> str:
    """One-line human summary (free preview / marketing surface)."""
    a = report["assessment"]
    u = report["utilization"]
    f = report["fees"]
    cost = report["settlement_cost"]["x402_settle"]["usd"]
    verb = a["verdict"].replace("_", " ").title()
    return (
        f"Base @ block {report['latest_block']}: {verb} - "
        f"{u['now_pct']}% full, {f['base_fee_gwei']} gwei, "
        f"x402 settle ~${cost:.4f}. Window {a['window'].split(' - ')[0]}."
    )
