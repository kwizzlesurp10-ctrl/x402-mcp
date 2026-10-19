"""P1: stats/operator surfaces never leak agent ids or the operator token."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import main as main_mod
from app.commerce import quota_store
from app.config import settings
from app.main import app
from app.operator_auth import agent_label, is_operator, redact_agent_ids
from app.ops_events import emit_tool_event

client = TestClient(app)
TOKEN = "op-secret-for-tests"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _fresh_stats_cache():
    main_mod._stats_cache.update({"time": None, "data": None})
    yield
    main_mod._stats_cache.update({"time": None, "data": None})


@pytest.fixture
def op_token(monkeypatch):
    monkeypatch.setattr(settings, "operator_token", TOKEN)
    return TOKEN


@pytest.fixture
def secret_agent():
    agent = "agent-must-not-leak-7f3a"
    quota_store.consume_quota(agent)
    return agent


def _req(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})


# ---- /stats -----------------------------------------------------------------


def test_public_stats_has_aggregates_but_no_agent_ids(op_token, secret_agent) -> None:
    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "public"
    assert body["agents"] == []
    assert secret_agent not in resp.text
    summary = body["summary"]
    assert summary["agent_count"] >= 1
    assert summary["calls_this_month_total"] >= 1
    assert "free" in summary["agents_by_tier"]
    assert body["config"]["free_tier_monthly_quota"] == 500


def test_public_stats_never_lists_agents_when_token_unset(monkeypatch, secret_agent) -> None:
    monkeypatch.setattr(settings, "operator_token", None)
    resp = client.get("/stats", headers={"Authorization": "Bearer None"})
    assert resp.json()["agents"] == []
    assert secret_agent not in resp.text


def test_wrong_token_gets_public_view(op_token, secret_agent) -> None:
    resp = client.get("/stats", headers={"Authorization": "Bearer nope"})
    assert resp.json()["scope"] == "public"
    assert secret_agent not in resp.text


def test_operator_stats_lists_agents(op_token, secret_agent) -> None:
    body = client.get("/stats", headers=AUTH).json()
    assert body["scope"] == "operator"
    assert secret_agent in {a["agent_id"] for a in body["agents"]}
    alt = client.get("/stats", headers={"X-Operator-Token": TOKEN}).json()
    assert alt["scope"] == "operator"


def test_cached_snapshot_does_not_leak_to_public(op_token, secret_agent) -> None:
    client.get("/stats", headers=AUTH)  # warm the cache as operator
    resp = client.get("/stats")
    assert resp.json()["agents"] == []
    assert secret_agent not in resp.text


# ---- operator auth primitive ---------------------------------------------------


def test_is_operator_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "operator_token", None)
    assert not is_operator(_req({"Authorization": "Bearer "}))
    assert not is_operator(_req({}))
    monkeypatch.setattr(settings, "operator_token", "")
    assert not is_operator(_req({"Authorization": "Bearer "}))
    monkeypatch.setattr(settings, "operator_token", TOKEN)
    assert is_operator(_req(AUTH))
    assert is_operator(_req({"Authorization": f"bearer {TOKEN}"}))
    assert not is_operator(_req({"Authorization": f"Bearer {TOKEN}x"}))
    assert not is_operator(_req({"Authorization": TOKEN}))


def test_redaction_is_stable_and_deep() -> None:
    data = {"agent_id": "a1", "nested": [{"buyer_agent_id": "b2", "tool": "t"}]}
    out = redact_agent_ids(data)
    assert out["agent_id"] == agent_label("a1") != "a1"
    assert out["nested"][0]["buyer_agent_id"].startswith("agt_")
    assert out["nested"][0]["tool"] == "t"
    assert data["agent_id"] == "a1"  # input untouched
    assert redact_agent_ids({"agent_id": None}) == {"agent_id": None}


# ---- /quota -------------------------------------------------------------------


def test_quota_requires_operator(op_token, secret_agent) -> None:
    assert client.get(f"/quota/{secret_agent}").status_code == 401
    assert client.get(f"/quota/{secret_agent}", headers={"Authorization": "Bearer x"}).status_code == 401
    ok = client.get(f"/quota/{secret_agent}", headers=AUTH)
    assert ok.status_code == 200
    assert ok.json()["meta"]["agent_id"] == secret_agent


# ---- /events SSE --------------------------------------------------------------


async def _first_tool_event(headers: dict[str, str]) -> dict:
    response = await main_mod.tool_events(_req(headers))
    iterator = response.body_iterator
    try:
        while True:
            chunk = await asyncio.wait_for(iterator.__anext__(), timeout=2)
            text = chunk if isinstance(chunk, str) else chunk.decode()
            event = json.loads(text.removeprefix("data: ").strip())
            if event.get("type") == "tool" and event.get("tool") == "redaction-probe":
                return event
    finally:
        await iterator.aclose()


@pytest.mark.asyncio
async def test_events_stream_redacts_agent_ids(op_token) -> None:
    emit_tool_event("redaction-probe", "agent-live-secret-91", {"agent_id": "agent-live-secret-91"})
    public = await _first_tool_event({})
    assert public["agent_id"] == agent_label("agent-live-secret-91")
    assert "agent-live-secret-91" not in json.dumps(public)
    operator = await _first_tool_event(AUTH)
    assert operator["agent_id"] == "agent-live-secret-91"


# ---- /swarm/runs ---------------------------------------------------------------


def test_swarm_runs_redacted_for_public(op_token, monkeypatch) -> None:
    monkeypatch.setattr(
        main_mod.swarm_registry,
        "recent_runs",
        lambda limit: [{"run_id": "r1", "agent_id": "caller-secret-1"}],
    )
    public = client.get("/swarm/runs")
    assert "caller-secret-1" not in public.text
    assert public.json()[0]["run_id"] == "r1"
    operator = client.get("/swarm/runs", headers=AUTH).json()
    assert operator[0]["agent_id"] == "caller-secret-1"


# ---- mutating operator actions ----------------------------------------------------


def test_pulse_publish_requires_operator(op_token, monkeypatch) -> None:
    monkeypatch.setattr(settings, "dashboard_actions", True)
    resp = client.post("/pulse/publish")
    assert resp.status_code == 401


def test_swarm_run_requires_operator(op_token, monkeypatch) -> None:
    monkeypatch.setattr(settings, "dashboard_actions", True)
    monkeypatch.setattr(settings, "swarm_enabled", True)
    resp = client.post("/swarm/run", json={"topic": "base gas", "agent_id": "victim"})
    assert resp.status_code == 401


# ---- dashboard never renders the token -------------------------------------------


def test_legacy_dashboard_does_not_embed_operator_token(op_token) -> None:
    html = client.get("/dashboard/legacy").text
    assert TOKEN not in html
    assert "__OP_TOKEN__" in html
    assert TOKEN not in main_mod.DASHBOARD_HTML


# ---- storefront monitor surfaces stay public ---------------------------------------


def test_monitor_surfaces_stay_public(op_token) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/doctor").status_code == 200
    assert client.get("/stats").status_code == 200
