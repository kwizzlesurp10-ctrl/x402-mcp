"""OPERATOR_TOKEN is required: unset -> operator routes 503 + startup error."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.operator_auth import OperatorTokenMissing, check_operator_token_at_startup

client = TestClient(app)


def test_quota_is_503_when_token_unset(monkeypatch) -> None:
    monkeypatch.setattr(settings, "operator_token", None)
    r = client.get("/quota/some-agent", headers={"Authorization": "Bearer guess"})
    assert r.status_code == 503
    assert r.json()["error"] == "operator_surface_disabled"


@pytest.mark.parametrize("path,method", [("/pulse/publish", "post")])
def test_operator_routes_503_when_token_unset(monkeypatch, path, method) -> None:
    monkeypatch.setattr(settings, "operator_token", None)
    monkeypatch.setattr(settings, "dashboard_actions", True)
    monkeypatch.setattr(settings, "swarm_enabled", True)
    r = getattr(client, method)(path, json={})
    assert r.status_code == 503


def test_quota_still_401_with_wrong_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "operator_token", "a" * 32)
    assert client.get("/quota/x", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_startup_logs_error_when_unset(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "operator_token", None)
    monkeypatch.setattr(settings, "require_operator_token", False)
    with caplog.at_level(logging.ERROR):
        assert check_operator_token_at_startup() is False
    assert "OPERATOR_TOKEN is not set" in caplog.text


def test_startup_refuses_when_required(monkeypatch) -> None:
    monkeypatch.setattr(settings, "operator_token", None)
    monkeypatch.setattr(settings, "require_operator_token", True)
    with pytest.raises(OperatorTokenMissing):
        check_operator_token_at_startup()


def test_startup_ok_when_set(monkeypatch) -> None:
    monkeypatch.setattr(settings, "operator_token", "b" * 40)
    assert check_operator_token_at_startup() is True
