"""Contract tests for wallet_read USDC constants — no live RPC required."""

from __future__ import annotations

from app.wallet_read import USDC_CONTRACTS

CIRCLE_BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


def test_sepolia_usdc_contract_is_circle_base_sepolia() -> None:
    _, _, sepolia_addr = USDC_CONTRACTS["sepolia"]
    assert sepolia_addr == CIRCLE_BASE_SEPOLIA_USDC


def test_sepolia_usdc_contract_is_valid_evm_address() -> None:
    _, _, sepolia_addr = USDC_CONTRACTS["sepolia"]
    assert sepolia_addr.startswith("0x")
    assert len(sepolia_addr) == 42
    hex_body = sepolia_addr[2:]
    assert len(hex_body) == 40
    assert all(c in "0123456789abcdefABCDEF" for c in hex_body)