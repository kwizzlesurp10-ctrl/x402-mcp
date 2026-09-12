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


def test_smtp_provider_ledgers_without_http_dispatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SMTP may pass doctor checks but send_agent_mail does not dispatch it."""
    ledger_file = tmp_path / "mailrail.jsonl"
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", ledger_file)
    monkeypatch.setattr(settings, "mailrail_enabled", True)
    monkeypatch.setattr(settings, "mailrail_provider", "smtp")
    monkeypatch.setattr(settings, "mailrail_smtp_url", "smtps://user:pass@smtp.example.com:465")
    _SEEN_KEYS.clear()

    calls: list[object] = []

    def fake_post(*_a: object, **_k: object) -> None:
        calls.append((_a, _k))
        raise AssertionError("SMTP must not issue HTTP dispatch")

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    res = send_agent_mail(
        "ops@localhost",
        "SMTP stanza",
        "doctor-only",
        event_id="smtp_no_dispatch",
    )
    assert res["status"] == "sent"
    assert res["delivered"] is True
    assert calls == []
    record = json.loads(ledger_file.read_text(encoding="utf-8").strip().splitlines()[0])
    assert record["provider"] == "smtp"
    assert record["status"] == "sent"


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


@pytest.mark.asyncio
async def test_mailrail_fastmcp_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mcp_server import mailrail_send, mailrail_status

    ledger_file = tmp_path / "mailrail.jsonl"
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", ledger_file)
    _SEEN_KEYS.clear()

    # Status check tool
    status_raw = await mailrail_status()
    status_data = json.loads(status_raw)
    assert status_data["data"]["status"] == "ok"
    assert "provider" in status_data["data"]

    # Send tool
    send_raw = await mailrail_send(
        to="agent-smith@network.ai",
        subject="Report ready",
        body="Findings attached.",
        event_id="mcp_test_01",
    )
    send_data = json.loads(send_raw)
    assert send_data["data"]["status"] == "ok"
    assert send_data["data"]["mailrail"]["delivered"] is True


def test_mailrail_http_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    ledger_file = tmp_path / "mailrail.jsonl"
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", ledger_file)
    _SEEN_KEYS.clear()

    client = TestClient(app)

    # Health check
    res_health = client.get("/mailrail/health")
    assert res_health.status_code == 200
    assert res_health.json()["ok"] is True

    # Empty ledger
    res_empty = client.get("/mailrail/ledger")
    assert res_empty.status_code == 200
    assert res_empty.json()["count"] == 0

    # Dispatch mail and re-query ledger
    send_agent_mail("auditor@market.org", "Audit receipt", "All green", event_id="http_ledger_01")
    res_ledger = client.get("/mailrail/ledger")
    assert res_ledger.status_code == 200
    body = res_ledger.json()
    assert body["count"] == 1
    assert body["events"][0]["event_id"] == "http_ledger_01"
    assert body["events"][0]["to"] == "auditor@market.org"

    # Inbound message ingestion
    inbox_file = tmp_path / "mailrail_inbox.jsonl"
    monkeypatch.setattr("app.mailrail.MAILRAIL_INBOX_FILE", inbox_file)

    res_inbound = client.post(
        "/mailrail/inbound",
        json={
            "sender": "partner-bot@bazaar.xyz",
            "subject": "Quote Request for MN Data @alice",
            "body": "Need pricing for 100 queries for @bob.",
            "metadata": {"origin": "bazaar"},
        },
    )
    assert res_inbound.status_code == 200
    inbound_data = res_inbound.json()
    assert inbound_data["status"] == "received"
    assert "`@alice`" in inbound_data["subject"]


    # Inbound inbox query
    res_inbox = client.get("/mailrail/inbox")
    assert res_inbox.status_code == 200
    inbox_body = res_inbox.json()
    assert inbox_body["count"] == 1
    assert inbox_body["inbox"][0]["from"] == "partner-bot@bazaar.xyz"

    # Telemetry Stats
    res_stats = client.get("/mailrail/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["outbound_total"] == 1
    assert stats["inbound_total"] == 1
    assert stats["dedup_keys_cached"] >= 1


@pytest.mark.asyncio
async def test_mailrail_inbound_mcp_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mcp_server import mailrail_inbound

    inbox_file = tmp_path / "mailrail_inbox.jsonl"
    monkeypatch.setattr("app.mailrail.MAILRAIL_INBOX_FILE", inbox_file)

    res_raw = await mailrail_inbound(
        sender="scout-agent@network.ai",
        subject="Service alert",
        body="Upstream pricing dropped.",
    )
    res_data = json.loads(res_raw)
    assert res_data["data"]["status"] == "ok"
    assert res_data["data"]["inbound"]["status"] == "received"
    assert res_data["data"]["inbound"]["from"] == "scout-agent@network.ai"



