"""Scheduled Pulse republish must exist and must not take down /health."""

from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

from app import main
from app.swarm import publisher


def test_pulse_refresh_loop_is_the_second_refresh_path() -> None:
    assert callable(publisher.pulse_refresh_loop)
    src = inspect.getsource(main._lifespan)
    assert "pulse_refresh_loop" in src
    assert "restore_pinned_listing" in src


def test_restore_failure_does_not_500_health(monkeypatch) -> None:
    async def boom() -> None:
        raise RuntimeError("facilitator 401")

    monkeypatch.setattr(publisher, "restore_pinned_listing", boom)
    client = TestClient(main.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
