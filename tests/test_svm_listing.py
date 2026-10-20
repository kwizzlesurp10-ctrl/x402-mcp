"""Seller-only SVM listing surface — solana:* advertised, no spend key required."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.payment_rails import SOLANA_MAINNET, build_payment_rails
from app.x402_services import svm_available

client = TestClient(app)


def test_payment_rails_advertise_solana_without_spend_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "evm_private_key", None)
    monkeypatch.setattr(settings, "svm_private_key", None)
    rails = build_payment_rails()
    svm = rails["x402_svm"]
    assert svm["pattern"] == "solana:*"
    assert svm["network"] == SOLANA_MAINNET
    assert svm["requires_env"] == ["X402_PAY_TO_ADDRESS"]
    assert "SVM_PRIVATE_KEY" not in svm["requires_env"]
    assert "EVM_PRIVATE_KEY" not in svm["requires_env"]
    assert svm["registered"] is svm_available()
    assert svm["facilitator_note"]


def test_agentic_market_and_funding_include_svm_rail(monkeypatch) -> None:
    monkeypatch.setattr(settings, "evm_private_key", None)
    monkeypatch.setattr(settings, "svm_private_key", None)
    market = client.get("/.well-known/agentic-market.json").json()
    funding = client.get("/.well-known/funding.json").json()
    assert market["settlement"]["payment_rails"]["x402_svm"]["pattern"] == "solana:*"
    assert funding["payment_rails"]["x402_svm"]["network"] == SOLANA_MAINNET
    ids = {s["id"] for s in market["services"]}
    assert "us-rental-diligence" in ids
    assert "base-tx-decision" in ids
