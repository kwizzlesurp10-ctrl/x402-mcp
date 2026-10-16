"""Public clients cannot invoke MailRail send/inbound/ledgers."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import mcp_server
from app.config import settings
from app.main import app
from app.tools_registry import EXPECTED_TOOL_NAMES, is_public_mcp_tool


def test_mailrail_tools_are_not_on_public_mcp_list() -> None:
    names = {t.name for t in mcp_server.mcp._tool_manager._tools.values()}
    assert names == EXPECTED_TOOL_NAMES
    for banned in ("mailrail.send", "mailrail.status", "mailrail.inbound"):
        assert banned not in names
        assert not is_public_mcp_tool(banned)


def test_unauthenticated_http_mailrail_message_routes_are_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "operator_token", None)
    client = TestClient(app)

    assert client.get("/mailrail/ledger").status_code == 401
    assert client.get("/mailrail/inbox").status_code == 401
    assert client.get("/mailrail/stats").status_code == 401
    inbound = client.post(
        "/mailrail/inbound",
        json={"sender": "public@evil.test", "subject": "hi", "body": "open relay?"},
    )
    assert inbound.status_code == 401
    detail = inbound.json().get("detail") or inbound.json()
    if isinstance(detail, dict):
        assert detail.get("error") == "unauthorized"
    else:
        assert "unauthorized" in str(detail).lower()


def test_wrong_bearer_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "operator_token", "s3cret")
    client = TestClient(app)
    headers = {"Authorization": "Bearer nope"}
    assert client.get("/mailrail/ledger", headers=headers).status_code == 401
    assert (
        client.post(
            "/mailrail/inbound",
            headers=headers,
            json={"sender": "a", "subject": "b", "body": "c"},
        ).status_code
        == 401
    )


def test_operator_bearer_without_mailrail_agent_is_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "operator_token", "s3cret")
    client = TestClient(app)
    res = client.get("/mailrail/ledger", headers={"Authorization": "Bearer s3cret"})
    assert res.status_code == 403
    detail = res.json().get("detail") or {}
    assert detail.get("error") == "forbidden"
    assert detail.get("required_agent_id") == "x402-mailrail-postmaster"


def test_operator_bearer_can_read_empty_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(settings, "operator_token", "s3cret")
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", tmp_path / "mailrail.jsonl")
    client = TestClient(app)
    res = client.get(
        "/mailrail/ledger",
        headers={
            "Authorization": "Bearer s3cret",
            "X-Agent-Id": "x402-mailrail-postmaster",
        },
    )
    assert res.status_code == 200
    assert res.json()["count"] == 0


def test_public_health_does_not_dump_recipients() -> None:
    client = TestClient(app)
    res = client.get("/mailrail/health")
    assert res.status_code == 200
    body = res.json()
    assert "admin_recipient" not in body
    assert "from_address" not in body
    assert "has_api_key" not in body
