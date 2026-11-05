"""AgentMail Svix webhook at /mailrail/webhooks/agentmail."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.mailrail import _SEEN_KEYS
from app.main import app

_SECRET_KEY = b"0123456789abcdef01234567"
_SECRET = "whsec_" + base64.b64encode(_SECRET_KEY).decode("ascii")


def _sign(body: bytes, msg_id: str = "msg_1", ts: int | None = None) -> dict[str, str]:
    timestamp = str(int(time.time()) if ts is None else ts)
    signed = f"{msg_id}.{timestamp}.".encode("utf-8") + body
    digest = hmac.new(_SECRET_KEY, signed, hashlib.sha256).digest()
    return {
        "svix-id": msg_id,
        "svix-timestamp": timestamp,
        "svix-signature": "v1," + base64.b64encode(digest).decode("ascii"),
    }


def _event(**message: object) -> bytes:
    payload = {
        "event_type": "message.received",
        "event_id": "evt_1",
        "message": {
            "from_": ["Ada <ada@example.com>"],
            "to": ["x402-mcp@agentmail.to"],
            "subject": "Hello MailRail",
            "text": "A signed inbound note.",
            "inbox_id": "x402-mcp@agentmail.to",
            "message_id": "<m1@agentmail.to>",
            **message,
        },
    }
    return json.dumps(payload).encode("utf-8")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("app.mailrail.MAILRAIL_INBOX_FILE", tmp_path / "inbox.jsonl")
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", tmp_path / "out.jsonl")
    monkeypatch.setattr(
        "app.mailrail_agent.notify_operator",
        lambda *args, **kwargs: {"skipped": True},
    )
    _SEEN_KEYS.clear()
    return TestClient(app)


def test_get_is_mounted_and_does_not_echo_the_secret(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mailrail_agentmail_webhook_secret", _SECRET)
    res = client.get("/mailrail/webhooks/agentmail")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["accepts"] == "POST"
    assert body["secret_configured"] is True
    assert _SECRET not in res.text
    assert "whsec_" not in res.text


def test_get_reports_secret_missing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mailrail_agentmail_webhook_secret", None)
    res = client.get("/mailrail/webhooks/agentmail")
    assert res.status_code == 200
    assert res.json()["secret_configured"] is False


def test_post_without_secret_is_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mailrail_agentmail_webhook_secret", None)
    body = _event()
    res = client.post(
        "/mailrail/webhooks/agentmail",
        content=body,
        headers={"content-type": "application/json", **_sign(body)},
    )
    assert res.status_code == 503
    assert res.json()["detail"]["error"] == "agentmail_webhook_unconfigured"


def test_bad_signature_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mailrail_agentmail_webhook_secret", _SECRET)
    body = _event()
    headers = _sign(body)
    headers["svix-signature"] = "v1," + base64.b64encode(b"nope-nope-nope-nope").decode()
    res = client.post("/mailrail/webhooks/agentmail", content=body, headers=headers)
    assert res.status_code == 401
    assert res.json()["detail"]["error"] == "invalid_signature"


def test_signed_message_received_is_ingested(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "mailrail_agentmail_webhook_secret", _SECRET)
    body = _event()
    res = client.post(
        "/mailrail/webhooks/agentmail",
        content=body,
        headers={"content-type": "application/json", **_sign(body)},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "received"
    assert payload["event_id"] == "evt_1"
    assert "A signed inbound note." not in res.text

    inbox = (tmp_path / "inbox.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(inbox) == 1
    record = json.loads(inbox[0])
    assert record["from"] == "Ada <ada@example.com>"
    assert record["subject"] == "Hello MailRail"
    assert record["metadata"]["source"] == "agentmail"
    assert record["metadata"]["to"] == ["x402-mcp@agentmail.to"]

    again = client.post(
        "/mailrail/webhooks/agentmail",
        content=body,
        headers={"content-type": "application/json", **_sign(body, msg_id="msg_2")},
    )
    assert again.status_code == 200
    assert again.json()["status"] == "duplicate"
    inbox_after = (tmp_path / "inbox.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(inbox_after) == 1


def test_other_event_types_are_ignored(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "mailrail_agentmail_webhook_secret", _SECRET)
    body = json.dumps(
        {"event_type": "message.sent", "event_id": "evt_sent", "send": {"inbox_id": "x"}}
    ).encode()
    res = client.post(
        "/mailrail/webhooks/agentmail",
        content=body,
        headers=_sign(body),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"
    assert not (tmp_path / "inbox.jsonl").exists()
