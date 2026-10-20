"""Base transaction finality check — real data only, no modeled probabilities.

Answers a different question than the other two Base products in this repo:
Pulse is a network snapshot, /base/tx-decision is a pre-submit fee/timing
call. This is post-submit: "I already sent this transaction — is it safe to
treat as irreversible yet?"

The OP-stack (Base's execution client) exposes its own consensus-safety
block tags over standard JSON-RPC: `eth_getBlockByNumber("safe"/"finalized",
false)`. Those come from L1-derived finality, not a guess — "safe" tracks
L1 attestation, "finalized" tracks L1 finality (~2 epochs). Comparing a
transaction's block against those tags is a real classification read off
the chain, not an invented reorg-probability number.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings
from app.pulse import _rpc

RESOURCE_DESCRIPTION = (
    "Base mainnet transaction finality check: given a tx hash, classifies it as "
    "not_found, pending, unsafe (sequencer-confirmed only), safe (L1-attested), "
    "or finalized (L1-finalized) -- read directly from the node's own safe/"
    "finalized block tags, not a modeled reorg probability. Input: tx hash. "
    "Output: JSON."
)

DISCOVERY_INPUT_EXAMPLE: dict[str, Any] = {
    "tx": "0x7fe54ef102682c07d2091d5623cb86df8be1ca929ae4cfb90fbdd6e73eba2c40"
}

DISCOVERY_OUTPUT_EXAMPLE: dict[str, Any] = {
    "tx": "0x7fe54ef102682c07d2091d5623cb86df8be1ca929ae4cfb90fbdd6e73eba2c40",
    "included": True,
    "status": "finalized",
    "tx_block": 49106777,
    "confirmations": 9563,
    "safe_block": 49116306,
    "finalized_block": 49115873,
    "latest_block": 49116340,
    "why": "Block 49106777 is at or behind the chain's 'finalized' block "
    "(49115873) -- L1-confirmed, reorg is not possible.",
    "as_of": "2026-07-25T23:00:00+00:00",
}


def resource_url() -> str:
    return f"{settings.public_base_url}/base/finality-check"


async def check_finality(tx_hash: str) -> dict[str, Any]:
    """Classify a Base mainnet tx hash against the chain's own safety tags."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        tx_result, safe_raw, finalized_raw, latest_raw = await asyncio.gather(
            _rpc(client, "eth_getTransactionByHash", [tx_hash]),
            _rpc(client, "eth_getBlockByNumber", ["safe", False]),
            _rpc(client, "eth_getBlockByNumber", ["finalized", False]),
            _rpc(client, "eth_getBlockByNumber", ["latest", False]),
        )

    safe_block = int(safe_raw["number"], 16)
    finalized_block = int(finalized_raw["number"], 16)
    latest_block = int(latest_raw["number"], 16)
    as_of = datetime.now(UTC).isoformat(timespec="seconds")

    base = {
        "tx": tx_hash,
        "safe_block": safe_block,
        "finalized_block": finalized_block,
        "latest_block": latest_block,
        "as_of": as_of,
    }

    if tx_result is None:
        return {
            **base,
            "included": False,
            "status": "not_found",
            "tx_block": None,
            "confirmations": None,
            "why": "No transaction found with this hash on Base mainnet -- "
            "never broadcast, dropped, or submitted on a different network.",
        }

    block_number_hex = tx_result.get("blockNumber")
    if block_number_hex is None:
        return {
            **base,
            "included": False,
            "status": "pending",
            "tx_block": None,
            "confirmations": None,
            "why": "Transaction is known to the mempool but not yet included "
            "in a block.",
        }

    tx_block = int(block_number_hex, 16)
    confirmations = max(0, latest_block - tx_block + 1)

    if tx_block <= finalized_block:
        status = "finalized"
        why = (
            f"Block {tx_block} is at or behind the chain's 'finalized' block "
            f"({finalized_block}) -- L1-confirmed, reorg is not possible."
        )
    elif tx_block <= safe_block:
        status = "safe"
        why = (
            f"Block {tx_block} is at or behind the 'safe' block ({safe_block}) "
            f"but ahead of 'finalized' ({finalized_block}) -- L1-attested, "
            "reorg risk is extremely low but not yet finalized."
        )
    else:
        status = "unsafe"
        why = (
            f"Block {tx_block} is ahead of the chain's 'safe' block "
            f"({safe_block}) -- only sequencer-confirmed so far "
            f"({confirmations} confirmation(s)); could still be reorged "
            "before L1 attestation."
        )

    return {
        **base,
        "included": True,
        "status": status,
        "tx_block": tx_block,
        "confirmations": confirmations,
        "why": why,
    }
