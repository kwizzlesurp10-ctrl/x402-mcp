"""Public wallet reads for mission-control — never serialize private keys."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings

# Base Sepolia + Base mainnet USDC (Circle) contract addresses
USDC_CONTRACTS: dict[str, tuple[str, str, str]] = {
    "sepolia": (
        "eip155:84532",
        "https://sepolia.base.org",
        "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    ),
    "mainnet": (
        "eip155:8453",
        "https://mainnet.base.org",
        "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    ),
}

FAUCET_URL = "https://docs.cdp.coinbase.com/faucets/introduction/quickstart"


def _vault_public_address() -> str | None:
    """Derive vault public address in-process; never return or log the private key."""
    if not settings.evm_private_key:
        return None
    from eth_account import Account

    return Account.from_key(settings.evm_private_key).address


def _balance_of_payload(address: str) -> str:
    """ERC-20 balanceOf(address) call data."""
    addr = address.lower().removeprefix("0x")
    padded = addr.rjust(64, "0")
    return f"0x70a08231{padded}"


async def _read_usdc_atomic(rpc_url: str, contract: str, address: str) -> int | None:
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [
            {"to": contract, "data": _balance_of_payload(address)},
            "latest",
        ],
        "id": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(rpc_url, json=payload)
            response.raise_for_status()
            result = response.json().get("result")
            if not result or result == "0x":
                return 0
            return int(result, 16)
    except Exception:
        return None


async def build_wallet_snapshot() -> dict[str, Any]:
    """Public addresses and USDC balances only."""
    receive_address = settings.x402_pay_to_address
    vault_address = _vault_public_address()

    balances: dict[str, int | None] = {
        "sepolia_usdc_atomic": None,
        "mainnet_usdc_atomic": None,
    }

    read_address = vault_address or receive_address
    if read_address:
        _, sepolia_rpc, sepolia_usdc = USDC_CONTRACTS["sepolia"]
        _, mainnet_rpc, mainnet_usdc = USDC_CONTRACTS["mainnet"]
        balances["sepolia_usdc_atomic"] = await _read_usdc_atomic(
            sepolia_rpc, sepolia_usdc, read_address
        )
        balances["mainnet_usdc_atomic"] = await _read_usdc_atomic(
            mainnet_rpc, mainnet_usdc, read_address
        )

    return {
        "receive_address": receive_address,
        "vault_address": vault_address,
        "balances": balances,
        "faucet_url": FAUCET_URL,
        "network": settings.x402_default_network,
        "note": "Private keys stay in server env; this endpoint never returns key material.",
    }