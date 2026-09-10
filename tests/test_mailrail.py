"""Tests for MailRail agent communication and transactional dispatch rail."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.config import settings
from app.mailrail import (
    defuse_mentions,
    event_key,
    format_settlement_receipt,
    send_agent_mail,
    _SEEN_KEYS,
)
from app.payment_rails import build_payment_rails


def test_payment_rails_catalog_includes_mailrail() -> None:
    rails = build_payment_rails()
    assert "mailrail" in rails
    assert rails["mailrail"]["primary"] is False
    assert "communication" in rails["mailrail"]["description"].lower() or "messaging" in rails["mailrail"]["description"].lower()


def test_event_key_stability() -> None:
    k1 = event_key("agent-01", "sale", "tx123")
    k2 = event_key("agent-01", "sale", "tx123")
    k3 = event_key("agent-01", "sale", "tx456")
    assert k1 == k2
    assert k1 != k3



def test_defuse_mentions_in_mail() -> None:
    raw = "Alert from @trader to @operator regarding issue @repo"
    cleaned = defuse_mentions(raw)
    assert "`@trader`" in cleaned
    assert "`@operator`" in cleaned
    assert "`@repo`" in cleaned


def test_send_agent_mail_mock_and_dedup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_file = tmp_path / "mailrail.jsonl"
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", ledger_file)
    _SEEN_KEYS.clear()

    res1 = send_agent_mail(
        to="operator@x402.org",
        subject="Settlement Alert @watch",
        body="Settled 10 USDC for scout-01",
        event_id="evt_test_001",
    )
    assert res1["status"] == "sent"
    assert res1["delivered"] is True
    assert "`@watch`" in res1["subject"]

    res2 = send_agent_mail(
        to="operator@x402.org",
        subject="Settlement Alert @watch",
        body="Settled 10 USDC for scout-01",
        event_id="evt_test_001",
    )
    assert res2["status"] == "deduplicated"
    assert res2["delivered"] is False

    assert ledger_file.exists()
    lines = ledger_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_id"] == "evt_test_001"
    assert record["to"] == "operator@x402.org"


def test_format_settlement_receipt() -> None:
    subject, body = format_settlement_receipt(
        payer="0x1234567890abcdef",
        amount_usdc=0.015,
        resource="/mn/property-check",
        tx_hash="0xabcd1234",
    )
    assert "0.0150" in subject
    assert "/mn/property-check" in subject
    assert "0x1234567890abcdef" in body
    assert "0xabcd1234" in body


def test_live_resend_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ledger_file = tmp_path / "mailrail.jsonl"
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", ledger_file)
    monkeypatch.setattr(settings, "mailrail_enabled", True)
    monkeypatch.setattr(settings, "mailrail_provider", "resend")
    monkeypatch.setattr(settings, "mailrail_api_key", "re_test_key_123")
    _SEEN_KEYS.clear()

    class FakeResponse:
        status_code = 200

    calls = []
    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)

    res = send_agent_mail("user@example.com", "Test Resend", "Body content", event_id="resend_01")
    assert res["status"] == "sent"
    assert res["delivered"] is True
    assert len(calls) == 1
    assert "api.resend.com" in calls[0][0]


def test_live_webhook_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ledger_file = tmp_path / "mailrail.jsonl"
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", ledger_file)
    monkeypatch.setattr(settings, "mailrail_enabled", True)
    monkeypatch.setattr(settings, "mailrail_provider", "webhook")
    monkeypatch.setattr(settings, "mailrail_webhook_url", "https://discord.test/api/webhooks/123")
    _SEEN_KEYS.clear()

    class FakeResponse:
        status_code = 204

    calls = []
    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)

    res = send_agent_mail("discord-channel", "Watcher Alert", "Issue detected", event_id="webhook_01")
    assert res["status"] == "sent"
    assert res["delivered"] is True
    assert len(calls) == 1
    assert "discord.test" in calls[0][0]

