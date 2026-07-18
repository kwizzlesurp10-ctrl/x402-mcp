"""Security KeyProvider tests — env deprecation seam, no behavior change."""

from __future__ import annotations

import pytest

from app import keyprovider, x402_services
from app.config import settings

# Well-known Anvil test key (public, not a real wallet).
TEST_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


def test_env_provider_returns_key_and_flags_insecure(monkeypatch):
    monkeypatch.setattr(settings, "evm_private_key", TEST_KEY)
    monkeypatch.setattr(settings, "key_provider", "env")
    p = keyprovider.get_key_provider()
    assert p.name == "env"
    assert p.get_private_key() == TEST_KEY
    d = p.describe()
    assert d["secure"] is False and d["configured"] is True


def test_unknown_provider_disables_signing(monkeypatch):
    monkeypatch.setattr(settings, "key_provider", "hsm-that-does-not-exist")
    p = keyprovider.get_key_provider()
    assert p.get_private_key() is None  # never signs with an unavailable provider


def test_security_posture_recommends_migration(monkeypatch):
    monkeypatch.setattr(settings, "evm_private_key", TEST_KEY)
    monkeypatch.setattr(settings, "key_provider", "env")
    posture = keyprovider.security_posture()
    assert posture["key_provider"]["secure"] is False
    assert any("keychain/hardware" in r for r in posture["recommendations"])


def test_build_client_uses_provider(monkeypatch):
    """The buyer client still derives the correct account through the seam."""
    monkeypatch.setattr(settings, "evm_private_key", TEST_KEY)
    monkeypatch.setattr(settings, "key_provider", "env")
    client = x402_services._build_x402_client()
    assert client is not None  # built without error via the KeyProvider


def test_build_client_raises_without_key(monkeypatch):
    monkeypatch.setattr(settings, "evm_private_key", None)
    with pytest.raises(ValueError, match="EVM_PRIVATE_KEY"):
        x402_services._build_x402_client()
