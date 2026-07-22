"""One-shot x402 purchase against any resource, with a hard price cap.

Generalizes scripts/seed_purchase.py, which is pinned to one upstream. The
recurring need is cataloging: CDP indexes a resource into the Bazaar discovery
catalog when it is *settled*, not when it is published, so a new paid endpoint
stays invisible until someone pays it once. Settling it yourself is the cheapest
way in — for a self-owned resource the money moves between your own wallets.

Safety: pays through the sole spender (x402_services.pay_and_fetch) with
max_price_usdc as a hard cap, so a resource that asks for more is refused rather
than paid. Nothing is written to the ledger unless the payment actually settled
on-chain.

  python scripts/settle_once.py --url https://host/resource --max-usdc 0.01
  python scripts/settle_once.py --url https://host/search --method POST \
      --body '{"query": "x402"}' --max-usdc 0.01

Note: the CDP facilitator returns a transient 502 often enough to matter. That
path is safe (no funds move, nothing is recorded) — just run it again.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from app import x402_services
from app.models import PayAndFetchInput
from app.swarm import ledger_writer

SETTLEMENT_TX_KEYS = ("transaction", "txHash", "tx_hash", "transactionHash", "tx")


def _extract_tx(settlement: object) -> str | None:
    if not isinstance(settlement, dict):
        return None
    for key in SETTLEMENT_TX_KEYS:
        if settlement.get(key):
            return str(settlement[key])
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="resource to pay for")
    parser.add_argument(
        "--max-usdc",
        type=float,
        required=True,
        help="hard cap; the payment is refused above this",
    )
    parser.add_argument("--method", default="GET")
    parser.add_argument("--body", default=None, help="request body (POST/PUT)")
    parser.add_argument(
        "--content-type",
        default="application/json",
        help="only sent when --body is given",
    )
    parser.add_argument(
        "--network",
        default="eip155:8453",
        help="Base mainnet by default — the CDP facilitator settles here",
    )
    parser.add_argument(
        "--label",
        default="settle",
        help="prefix for the generated agent_id in the ledger row",
    )
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = uuid.uuid4().hex
    agent_id = f"{args.label}-{run_id[:8]}"

    print(f"[settle] agent_id={agent_id}")
    print(f"[settle] paying {args.url}")
    print(f"[settle] network={args.network} cap=${args.max_usdc:.6f}")

    result = await x402_services.pay_and_fetch(
        PayAndFetchInput(
            url=args.url,
            method=args.method.upper(),
            headers={"Content-Type": args.content_type} if args.body else None,
            body=args.body,
            preferred_network=args.network,
            max_price_usdc=args.max_usdc,
        )
    )

    settled = bool(result.get("payment_settled"))
    tx = _extract_tx(result.get("payment_settlement"))
    print(f"[settle] status_code={result.get('status_code')} settled={settled}")
    print(f"[settle] tx={tx}")
    print(f"[settle] body={str(result.get('body', ''))[:300]!r}")

    if not settled:
        # verify/settle failed upstream — no funds moved, so record nothing.
        print(f"[settle] NOT settled: {result.get('settlement_parse_error')}")
        print("[settle] no funds moved, nothing recorded. Transient 502s retry fine.")
        return 1

    ledger_writer.record_spend(
        agent_id=agent_id,
        amount_usdc=args.max_usdc,
        network=args.network,
        url=args.url,
        run_id=run_id,
        tx=tx,
        settled=True,
    )
    print(f"[settle] SETTLED ${args.max_usdc:.6f} USDC, recorded to ledger.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
