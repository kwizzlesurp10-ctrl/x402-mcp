"""MailRail is only available to the dedicated postmaster agent."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.mailrail_agent import AGENT_ID, agent_card, is_mailrail_agent, refuse_if_not_mailrail_agent
from app.main import app
from app.mcp_server import mailrail_send


def _auth(agent_id: str = AGENT_ID) -> dict[str, str]:
    return {"Authorization": "Bearer s3cret", "X-Agent-Id": agent_id}


def test_postmaster_is_the_only_default_mailrail_agent() -> None:
    assert is_mailrail_agent(AGENT_ID)
    assert not is_mailrail_agent(None)
    assert not is_mailrail_agent("public-buyer")
    assert not is_mailrail_agent("stranger")
    refused = refuse_if_not_mailrail_agent("buyer-1")
    assert refused is not None
    assert refused["error"]["code"] == "forbidden"


def test_agent_card_is_not_public_and_names_notify_email() -> None:
    card = agent_card()
    assert card["id"] == AGENT_ID
    assert card["public"] is False
    assert card["sole_responsibility"] == "mailrail"
    assert card["notify"]["email"] in {settings.contact_email, "kwizzlesurp10@gmail.com"}


def test_public_agent_card_route() -> None:
    client = TestClient(app)
    res = client.get("/agent/mailrail")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == AGENT_ID
    assert "inbound" in body["endpoints"]
    assert "OPERATOR_TOKEN" in str(body["auth"])


def test_wrong_agent_id_is_403(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "operator_token", "s3cret")
    client = TestClient(app)
    res = client.get("/mailrail/ledger", headers=_auth("not-the-postmaster"))
    assert res.status_code == 403


def test_postmaster_agent_can_inbound(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "operator_token", "s3cret")
    monkeypatch.setattr("app.mailrail.MAILRAIL_INBOX_FILE", tmp_path / "inbox.jsonl")
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", tmp_path / "outbox.jsonl")
    client = TestClient(app)
    res = client.post(
        "/mailrail/inbound",
        headers=_auth(),
        json={"sender": "a@b.c", "subject": "hi", "body": "from postmaster"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "received"
    assert body["agent_id"] == AGENT_ID


@pytest.mark.asyncio
async def test_mcp_send_refuses_non_postmaster_agent() -> None:
    raw = await mailrail_send(
        to="x@y.z",
        subject="nope",
        body="public",
        agent_id="random-buyer",
    )
    data = json.loads(raw)
    assert data["error"]["code"] == "forbidden"
    assert data["data"] is None


@pytest.mark.asyncio
async def test_mcp_send_allows_postmaster(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", tmp_path / "out.jsonl")
    raw = await mailrail_send(
        to="kwizzlesurp10@gmail.com",
        subject="postmaster ok",
        body="agent-only",
        event_id="agent-send-1",
        agent_id=AGENT_ID,
    )
    data = json.loads(raw)
    assert data["data"]["status"] == "ok"
    assert data["data"]["mailrail"]["agent_id"] == AGENT_ID


def test_notify_operator_github_when_token_set(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.mailrail_agent as ma

    monkeypatch.setattr(settings, "github_token", "ghs_test")
    monkeypatch.setattr(settings, "github_repo", "kwizzlesurp10-ctrl/x402-mcp")

    class _Resp:
        status_code = 201

        def json(self) -> dict:
            return {"html_url": "https://github.com/kwizzlesurp10-ctrl/x402-mcp/issues/1", "number": 1}

        @property
        def text(self) -> str:
            return ""

    def fake_post(url, **kwargs):
        assert "issues" in url
        assert kwargs["json"]["labels"] == ["mailrail"]
        return _Resp()

    monkeypatch.setattr(ma.httpx, "post", fake_post)
    out = ma.notify_operator("MailRail test", "body", event_id="n1", already_emailed=True)
    assert out["channels"]["github"]["ok"] is True
    assert out["channels"]["github"]["number"] == 1
