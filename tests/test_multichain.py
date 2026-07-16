"""Multi-chain (EVM + Solana/SVM) tests — real scheme registration, no mocks."""

from __future__ import annotations

import httpx
import pytest

from app import x402_services
from app.config import settings
from app.models import BuildSellerRequirementsInput

SOLANA_MAINNET = "solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1"


def test_server_registers_evm_and_solana():
    from x402 import x402ResourceServer

    server = x402ResourceServer(x402_services._facilitator_client())
    registered = x402_services._register_server_schemes(server)
    assert "eip155:*" in registered
    # svm extra is a declared dependency -> solana:* must register
    assert x402_services.svm_available()
    assert "solana:*" in registered


@pytest.mark.asyncio
async def test_solana_seller_requirements_build_live():
    """Real Solana mainnet seller listing (the marketing/code contradiction fix)."""
    try:
        r = x402_services.build_seller_requirements(
            BuildSellerRequirementsInput(
                network=SOLANA_MAINNET,
                pay_to="EtWTRABZaYq6iMfeYKouRu166VU2xqa15aTFDLzQarn",  # base58 pubkey
                price="$0.10",
                description="Base Network Pulse (Solana rail)",
            )
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        pytest.skip(f"facilitator unavailable: {exc}")
    assert r["network"] == SOLANA_MAINNET
    assert len(r["requirements"]) == 1
    assert r["requirements"][0]["scheme"] == "exact"


def test_buyer_client_solana_only(monkeypatch):
    """A Solana keypair alone builds a buyer client (no EVM key required)."""
    from solders.keypair import Keypair

    kp = Keypair()
    monkeypatch.setattr(settings, "evm_private_key", None)
    monkeypatch.setattr(settings, "svm_private_key", str(kp))  # base58 secret
    client = x402_services._build_x402_client(preferred_network=SOLANA_MAINNET)
    assert client is not None


def test_buyer_requires_at_least_one_key(monkeypatch):
    monkeypatch.setattr(settings, "evm_private_key", None)
    monkeypatch.setattr(settings, "svm_private_key", None)
    with pytest.raises(ValueError, match="EVM_PRIVATE_KEY"):
        x402_services._build_x402_client()
