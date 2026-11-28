"""Tests for AgentMail MailRail outbound dispatch and inbound webhooks."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from svix.webhooks import Webhook

from app.config import settings
from app.mailrail import _SEEN_KEYS, send_agent_mail
from app.mailrail_agentmail import (
    AgentMailWebhookVerificationError,
    parse_message_received,
    verify_agentmail_webhook,
)


def _whsec_secret() -> str:
    return "whsec_" + base64.b64encode(os.urandom(24)).decode()


def _signed_payload(secret: str, payload: dict) -> tuple[bytes, dict[str, str]]:
    wh = Webhook(secret)
    body_str = json.dumps(payload)
    body = body_str.encode("utf-8")
    ts = datetime.now(timezone.utc)
    msg_id = "msg_test_svix_id"
    signature = wh.sign(msg_id, ts, body_str)
    headers = {
        "svix-id": msg_id,
        "svix-timestamp": str(int(ts.timestamp())),
        "svix-signature": signature,
    }
    return body, headers


def test_parse_message_received_maps_fields() -> None:
    payload = {
        "event_type": "message.received",
        "event_id": "evt_abc",
        "message": {
            "from": "Jane Doe <jane@example.com>",
            "subject": "Hello MailRail",
            "text": "Plain body",
            "message_id": "<mid@agentmail.to>",
            "thread_id": "thd_1",
            "inbox_id": "x402-mcp@agentmail.to",
        },
        "thread": {"message_count": 2},
    }
    parsed = parse_message_received(payload)
    assert parsed is not None
    sender, subject, body, meta = parsed
    assert sender == "jane@example.com"
    assert subject == "Hello MailRail"
    assert body == "Plain body"
    assert meta["agentmail_event_id"] == "evt_abc"
    assert meta["message_id"] == "<mid@agentmail.to>"
    assert meta["thread_message_count"] == 2


def test_live_agentmail_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ledger_file = tmp_path / "mailrail.jsonl"
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", ledger_file)
    monkeypatch.setattr(settings, "mailrail_enabled", True)
    monkeypatch.setattr(settings, "mailrail_provider", "agentmail")
    monkeypatch.setattr(settings, "mailrail_api_key", "am_test_key")
    monkeypatch.setattr(settings, "mailrail_from_address", "x402-mcp@agentmail.to")
    _SEEN_KEYS.clear()

    class FakeResponse:
        status_code = 200

    calls: list[tuple[str, dict]] = []

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        calls.append((url, kwargs))  # type: ignore[arg-type]
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)

    res = send_agent_mail(
        "ops@example.com",
        "AgentMail test",
        "Body",
        event_id="agentmail_out_01",
    )
    assert res["status"] == "sent"
    assert res["delivered"] is True
    assert len(calls) == 1
    assert "api.agentmail.to" in calls[0][0]
    assert "x402-mcp%40agentmail.to" in calls[0][0]
    json_body = calls[0][1]["json"]
    assert json_body["to"] == "ops@example.com"
    assert json_body["subject"] == "AgentMail test"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer am_test_key"


def test_agentmail_webhook_rejects_invalid_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = _whsec_secret()
    monkeypatch.setattr(settings, "mailrail_agentmail_webhook_secret", secret)
    body = b'{"event_type":"message.received"}'
    with pytest.raises(AgentMailWebhookVerificationError):
        verify_agentmail_webhook(body, {"svix-id": "x", "svix-timestamp": "1", "svix-signature": "v1,bad"})


def test_agentmail_webhook_route_accepts_valid_signature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    secret = _whsec_secret()
    monkeypatch.setattr(settings, "mailrail_agentmail_webhook_secret", secret)
    inbox_file = tmp_path / "inbox.jsonl"
    monkeypatch.setattr("app.mailrail.MAILRAIL_INBOX_FILE", inbox_file)
    monkeypatch.setattr(
        "app.mailrail_agent.notify_operator",
        lambda *a, **k: {"status": "skipped"},
    )

    payload = {
        "event_type": "message.received",
        "event_id": "evt_webhook_1",
        "message": {
            "from": "sender@external.test",
            "subject": "Inbound via AgentMail",
            "text": "Webhook body",
            "message_id": "<w@agentmail.to>",
            "thread_id": "thd_w",
            "inbox_id": "x402-mcp@agentmail.to",
        },
        "thread": {"message_count": 1},
    }
    body, headers = _signed_payload(secret, payload)

    client = TestClient(app)
    res = client.post("/mailrail/webhooks/agentmail", content=body, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "received"
    assert data["from"] == "sender@external.test"
    assert data["subject"] == "Inbound via AgentMail"
    assert data["source"] == "agentmail_webhook"
    assert inbox_file.exists()


def test_agentmail_webhook_route_rejects_bad_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(settings, "mailrail_agentmail_webhook_secret", _whsec_secret())
    client = TestClient(app)
    res = client.post(
        "/mailrail/webhooks/agentmail",
        content=b"{}",
        headers={
            "svix-id": "msg_bad",
            "svix-timestamp": "1234567890",
            "svix-signature": "v1,invalid",
        },
    )
    assert res.status_code == 400


def test_agentmail_webhook_ignores_other_event_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    secret = _whsec_secret()
    monkeypatch.setattr(settings, "mailrail_agentmail_webhook_secret", secret)
    body, headers = _signed_payload(secret, {"event_type": "message.sent", "event_id": "x"})
    client = TestClient(app)
    res = client.post("/mailrail/webhooks/agentmail", content=body, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"
