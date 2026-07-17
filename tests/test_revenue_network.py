"""Revenue-network coherence guard: resolution rules + doctor fail-state."""

from __future__ import annotations

from app.config import settings
from app.doctor import run_checks
from app.x402_services import resolve_revenue_network


def _clear_cdp(monkeypatch) -> None:
    monkeypatch.setattr(settings, "cdp_api_key_id", None)
    monkeypatch.setattr(settings, "cdp_api_key_secret", None)


def test_bare_default_resolves_default_network(monkeypatch) -> None:
    _clear_cdp(monkeypatch)
    monkeypatch.setattr(settings, "revenue_network", None)
    monkeypatch.setattr(settings, "x402_default_network", "eip155:84532")
    assert resolve_revenue_network() == "eip155:84532"


def test_cdp_creds_resolve_first_cdp_network(monkeypatch) -> None:
    monkeypatch.setattr(settings, "revenue_network", None)
    monkeypatch.setattr(settings, "cdp_api_key_id", "key")
    monkeypatch.setattr(settings, "cdp_api_key_secret", "secret")
    monkeypatch.setattr(settings, "cdp_networks", "eip155:8453,eip155:137")
    assert resolve_revenue_network() == "eip155:8453"


def test_explicit_override_wins(monkeypatch) -> None:
    monkeypatch.setattr(settings, "revenue_network", "eip155:137")
    monkeypatch.setattr(settings, "cdp_api_key_id", "key")
    monkeypatch.setattr(settings, "cdp_api_key_secret", "secret")
    assert resolve_revenue_network() == "eip155:137"


def _revenue_check(report: dict) -> dict:
    return next(c for c in report["checks"] if c["id"] == "revenue_network")


def test_doctor_fails_public_testnet_revenue(monkeypatch) -> None:
    _clear_cdp(monkeypatch)
    monkeypatch.setattr(settings, "revenue_network", None)
    monkeypatch.setattr(settings, "x402_default_network", "eip155:84532")
    monkeypatch.setattr(settings, "x402_pay_to_address", "0x" + "1" * 40)
    monkeypatch.setattr(settings, "public_base_url", "https://pulse.example.com")
    check = _revenue_check(run_checks())
    assert check["status"] == "fail"
    assert "testnet" in check["message"]


def test_doctor_passes_local_testnet_revenue(monkeypatch) -> None:
    _clear_cdp(monkeypatch)
    monkeypatch.setattr(settings, "revenue_network", None)
    monkeypatch.setattr(settings, "x402_default_network", "eip155:84532")
    monkeypatch.setattr(settings, "x402_pay_to_address", "0x" + "1" * 40)
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8402")
    assert _revenue_check(run_checks())["status"] == "pass"


def test_doctor_passes_public_mainnet_revenue(monkeypatch) -> None:
    monkeypatch.setattr(settings, "revenue_network", "eip155:8453")
    monkeypatch.setattr(settings, "x402_pay_to_address", "0x" + "1" * 40)
    monkeypatch.setattr(settings, "public_base_url", "https://pulse.example.com")
    check = _revenue_check(run_checks())
    assert check["status"] == "pass"
    assert check["message"] == "eip155:8453"
