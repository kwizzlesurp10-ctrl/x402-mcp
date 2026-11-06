"""A2A task durability when REDIS_URL + shared fakeredis client."""

from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.agent_surface import A2A_X402_EXTENSION_URI
from app import a2a_task_store
from app.a2a_rpc import META_STATUS, clear_task_store
from app.config import settings
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fakeredis_a2a(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind quota + A2A + MCP settlement to one fakeredis."""
    from app import commerce, mcp_settlement_store, redis_client

    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "client", r)
    monkeypatch.setattr(redis_client, "fallback_reason", None)
    monkeypatch.setattr(commerce, "quota_store", commerce.build_quota_store())
    monkeypatch.setattr(mcp_settlement_store, "_CLIENT", r)
    monkeypatch.setattr(settings, "redis_url", "redis://fake")
    monkeypatch.setattr(settings, "a2a_task_store_redis", True)
    yield
    clear_task_store()
    a2a_task_store.clear_for_test()


def test_task_survives_clear_memory_cache(client: TestClient) -> None:
    from app import a2a_rpc

    resp = client.post(
        "/a2a",
        headers={"X-A2A-Extensions": A2A_X402_EXTENSION_URI},
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [],
                    "metadata": {
                        "skillId": "us-cities-catalog",
                        "input": {},
                    },
                }
            },
        },
    )
    tid = resp.json()["result"]["id"]
    cap = resp.json()["result"]["capabilityToken"]

    a2a_rpc._TASKS_MEM.clear()

    got = client.post(
        "/a2a",
        headers={"X-A2A-Task-Capability": cap},
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/get",
            "params": {"id": tid},
        },
    )
    assert got.json()["result"]["id"] == tid


def test_capability_digest_auth_roundtrip(client: TestClient) -> None:
    resp = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [],
                    "metadata": {
                        "skillId": "us-cities-catalog",
                        "input": {},
                    },
                }
            },
        },
    )
    tid = resp.json()["result"]["id"]
    cap = resp.json()["result"]["capabilityToken"]

    bad = client.post(
        "/a2a",
        headers={"X-A2A-Task-Capability": "not-the-token"},
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/get",
            "params": {"id": tid},
        },
    )
    assert bad.json().get("error", {}).get("code") == -32003

    raw = a2a_task_store.get_task(tid)
    assert raw is not None
    assert isinstance(raw.get("capability_token"), str)
    assert isinstance(raw.get("capability_digest"), str)

    ok = client.post(
        "/a2a",
        headers={"X-A2A-Task-Capability": cap},
        json={
            "jsonrpc": "2.0",
            "id": "3",
            "method": "tasks/get",
            "params": {"id": tid},
        },
    )
    assert ok.json()["result"]["id"] == tid


def test_paid_task_retry_skips_verify_when_receipt_has_tx(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock
    from types import SimpleNamespace

    from app import a2a_rpc

    _calls = {"n": 0}

    async def _fake_verify_settle(_sig: str, _header: str) -> dict:
        _calls["n"] += 1
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0xdeadbeef", "network": "eip155:84532"},
        }

    start = client.post(
        "/a2a",
        headers={"X-A2A-Extensions": A2A_X402_EXTENSION_URI},
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [],
                    "metadata": {
                        "skillId": "base-tx-decision",
                        "input": {"gas": "usdc", "urgency": "flexible"},
                    },
                }
            },
        },
    )
    tid = start.json()["result"]["id"]
    cap = start.json()["result"]["capabilityToken"]

    stored = a2a_rpc._get_task_record(tid)
    assert stored is not None
    stored["receipts"] = [
        {"success": True, "transaction": "0xdeadbeef", "network": settings.x402_default_network},
    ]
    stored["binding"] = SimpleNamespace(
        verify_and_settle=_fake_verify_settle,
        execute=AsyncMock(return_value={"retry_path": True}),
        record_revenue=None,
    )
    a2a_rpc._persist_task(tid, stored)

    body = {
        "x402Version": 2,
        "payload": {"signature": "0x", "authorization": {}},
        "accepted": {"payTo": "0x" + "11" * 20},
    }
    pay = {
        "jsonrpc": "2.0",
        "id": "2",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [],
                "taskId": tid,
                "metadata": {
                    META_STATUS: "payment-submitted",
                    "x402.task.capability": cap,
                    "x402.payment.payload": body,
                },
            }
        },
    }
    r2 = client.post("/a2a", json=pay)
    assert r2.json()["result"]["status"]["state"] == "completed"
    assert _calls["n"] == 0
