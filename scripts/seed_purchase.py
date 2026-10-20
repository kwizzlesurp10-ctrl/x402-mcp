"""One-shot $0.01 seed purchase from a proven upstream x402 service.

Mirrors app/swarm/roles.py::treasurer_buy for a single buy: pays via the sole
spender (x402_services.pay_and_fetch) with a hard max_price_usdc cap so the
spend can NEVER exceed the seed amount, then records the settled spend to the
ledger (cost basis). Base mainnet (eip155:8453), settled through the CDP
facilitator. Target defaults to the Tavily x402 search endpoint, which has
four prior settled $0.01 buys in ledger/spend.jsonl.
"""

from __future__ import annotations

import asyncio
import json
import uuid

from app import x402_services
from app.models import PayAndFetchInput
from app.swarm import ledger_writer

URL = "https://x402.tavily.com/search"
NETWORK = "eip155:8453"        # Base mainnet — CDP facilitator settles here
SEED_USDC = 0.01               # hard cap: payment refused above this
QUERY = "x402 micropayment protocol on Base network"


async def main() -> int:
    run_id = uuid.uuid4().hex
    agent_id = f"seed-{run_id[:8]}"
    print(f"[seed] run_id={run_id} agent_id={agent_id}")
    print(f"[seed] paying {URL} on {NETWORK}, cap=${SEED_USDC:.2f} USDC ...")

    result = await x402_services.pay_and_fetch(
        PayAndFetchInput(
            url=URL,
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"query": QUERY}),
            preferred_network=NETWORK,
            max_price_usdc=SEED_USDC,
        )
    )

    settled = bool(result.get("payment_settled"))
    settlement = result.get("payment_settlement") or {}
    tx = None
    if isinstance(settlement, dict):
        for key in ("transaction", "txHash", "tx_hash", "transactionHash", "tx"):
            if settlement.get(key):
                tx = str(settlement[key])
                break

    print(f"[seed] status_code={result.get('status_code')} settled={settled}")
    print(f"[seed] settle_error={result.get('settlement_parse_error')}")
    print(f"[seed] tx={tx}")
    print(f"[seed] body_preview={str(result.get('body', ''))[:300]!r}")

    if not settled:
        print("[seed] NOT settled — no funds moved, nothing recorded.")
        return 1

    ledger_writer.record_spend(
        agent_id=agent_id,
        amount_usdc=SEED_USDC,
        network=NETWORK,
        url=URL,
        run_id=run_id,
        tx=tx,
        settled=True,
    )
    print(f"[seed] SETTLED ${SEED_USDC:.2f} USDC, recorded to ledger. tx={tx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
