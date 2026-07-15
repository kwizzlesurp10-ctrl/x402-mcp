"""Mission-control ops endpoints — stats, events, ledger."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.commerce import InMemoryQuotaStore
from app.main import app
from app import ledger_io
from app.ops_events import emit_tool_event, recent_events

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_stats_snapshot() -> None:
    response = client.get("/stats")
    assert response.status_code == 200
    body = response.json()
    assert "agents" in body
    assert "config" in body
    assert body["config"]["free_tier_monthly_quota"] == 500


def test_ledger_spend_empty() -> None:
    response = client.get("/ledger/spend")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body == []


def test_ledger_reads_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    (ledger_dir / "spend.jsonl").write_text(
        '{"ts":"2026-01-01","amount_usdc":0.01}\n'
        '{"ts":"2026-01-02","amount_usdc":0.02}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(ledger_io, "LEDGER", ledger_dir)
    rows = ledger_io.read_ledger_rows("spend")
    assert len(rows) == 2
    assert rows[0]["ts"] == "2026-01-02"


def test_emit_tool_event_records() -> None:
    emit_tool_event(
        "get_supported_networks",
        "scout-01",
        {"tier": "free", "quota_remaining": 499},
    )
    events = recent_events()
    assert events[-1]["tool"] == "get_supported_networks"
    assert events[-1]["agent_id"] == "scout-01"


@pytest.mark.asyncio
async def test_execute_tool_emits_event(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import mcp_server

    store = InMemoryQuotaStore()
    monkeypatch.setattr(mcp_server, "quota_store", store)

    await mcp_server.get_supported_networks(agent_id="ops-test-agent")

    events = recent_events()
    assert any(e["agent_id"] == "ops-test-agent" for e in events)


def test_commerce_snapshot_lists_agents() -> None:
    store = InMemoryQuotaStore()
    store.consume_quota("snap-a")
    store.consume_quota("snap-b")
    snap = store.snapshot()
    ids = {a["agent_id"] for a in snap["agents"]}
    assert "snap-a" in ids
    assert "snap-b" in ids