"""POST /a2a JSON-RPC with x402-a2a payment metadata."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agent_surface import A2A_X402_EXTENSION_URI
from app.a2a_rpc import META_REQUIRED, META_STATUS, clear_task_store
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_a2a_tasks() -> None:
    clear_task_store()
    yield
    clear_task_store()


def test_a2a_message_send_unpaid_returns_input_required() -> None:
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
                    "parts": [{"kind": "text", "text": "tx decision"}],
                    "metadata": {
                        "skillId": "base-tx-decision",
                        "input": {"gas": "usdc", "urgency": "flexible"},
                    },
                }
            },
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-A2A-Extensions") == A2A_X402_EXTENSION_URI
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    task = body["result"]
    assert task["kind"] == "task"
    assert task["status"]["state"] == "input-required"
    meta = task["status"]["message"]["metadata"]
    assert meta[META_STATUS] == "payment-required"
    assert meta[META_REQUIRED]["x402Version"] == 2
    assert meta[META_REQUIRED]["accepts"]


def test_a2a_tasks_get_round_trip() -> None:
    send = client.post(
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
    task_id = send.json()["result"]["id"]
    got = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/get",
            "params": {"id": task_id},
        },
    )
    assert got.json()["result"]["id"] == task_id
    assert got.json()["result"]["status"]["state"] == "completed"


def test_a2a_tasks_cancel() -> None:
    send = client.post(
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
                        "skillId": "base-tx-decision",
                        "input": {"gas": "usdc", "urgency": "now"},
                    },
                }
            },
        },
    )
    task_id = send.json()["result"]["id"]
    canceled = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "3",
            "method": "tasks/cancel",
            "params": {"id": task_id},
        },
    )
    assert canceled.json()["result"]["status"]["state"] == "canceled"


def test_legacy_extension_uri_still_activates() -> None:
    from app.agent_surface import A2A_X402_LEGACY_EXTENSION_URI
    from app.a2a_rpc import extension_activation_response_headers

    assert extension_activation_response_headers(A2A_X402_LEGACY_EXTENSION_URI) == {
        "X-A2A-Extensions": A2A_X402_LEGACY_EXTENSION_URI
    }
    assert extension_activation_response_headers(A2A_X402_EXTENSION_URI) == {
        "X-A2A-Extensions": A2A_X402_EXTENSION_URI
    }


def test_agent_card_points_at_a2a_jsonrpc() -> None:
    card = client.get("/.well-known/agent-card.json").json()
    assert card["url"].endswith("/a2a")
    bindings = {i["protocolBinding"]: i["url"] for i in card["supportedInterfaces"]}
    assert bindings["JSONRPC"].endswith("/a2a")


def test_well_known_x402_lists_property_due_diligence_agent() -> None:
    body = client.get("/.well-known/x402").json()
    urls = body["resources"]
    assert any(u.endswith("/agent/property-due-diligence") for u in urls)


def test_mcp_redirect_respects_forwarded_proto() -> None:
    # /mcp itself is now served directly (McpBarePathAliasMiddleware), so use
    # the trailing-slash form, which still redirects to /mcp/mcp.
    resp = client.post(
        "/mcp/mcp/",
        headers={"X-Forwarded-Proto": "https", "Host": "x402-mcp.onrender.com"},
        follow_redirects=False,
    )
    if resp.status_code in {307, 308}:
        location = resp.headers.get("location", "")
        assert location.startswith("https://"), location
