"""Mission-control integration: stats echo, seller gate, SSE heartbeat."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ops_events import HEARTBEAT_INTERVAL_SECONDS, event_stream

client = TestClient(app)


def test_stats_config_echo_fields() -> None:
    body = client.get("/stats").json()
    config = body["config"]
    assert "has_pay_to" in config
    assert "has_buyer_key" in config
    assert config["redis_mode"] in ("memory", "redis")
    assert "network" in config
    assert "stripe_configured" in config


def test_ledger_returns_top_level_array() -> None:
    body = client.get("/ledger/spend").json()
    assert isinstance(body, list)


def test_seller_requirements_blocked_by_default() -> None:
    response = client.post(
        "/seller/requirements",
        json={"network": "eip155:84532", "price": "$0.01"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sse_emits_heartbeat_within_timeout() -> None:
    events: list[dict] = []

    async def collect():
        async for event in event_stream():
            events.append(event)
            if event.get("type") == "heartbeat":
                return

    await asyncio.wait_for(collect(), timeout=HEARTBEAT_INTERVAL_SECONDS + 5)
    assert any(e.get("type") == "heartbeat" for e in events)