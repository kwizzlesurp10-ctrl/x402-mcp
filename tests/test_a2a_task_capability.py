"""A2A task capability — cross-client and client-id binding."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agent_surface import A2A_X402_EXTENSION_URI
from app.a2a_rpc import META_STATUS, clear_task_store
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_tasks() -> None:
    clear_task_store()
    yield
    clear_task_store()


def _start_paid_task(
    client: TestClient, *, client_id: str | None = None
) -> tuple[str, str]:
    """Return (task_id, capability_token)."""
    headers: dict[str, str] = {"X-A2A-Extensions": A2A_X402_EXTENSION_URI}
    if client_id is not None:
        headers["X-A2A-Client-Id"] = client_id
    resp = client.post(
        "/a2a",
        headers=headers,
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
    task = resp.json()["result"]
    assert task["status"]["state"] == "input-required"
    tid = task["id"]
    cap = task["capabilityToken"]
    assert isinstance(tid, str) and tid
    assert isinstance(cap, str) and len(cap) > 16
    return tid, cap


def test_tasks_get_requires_capability(client: TestClient) -> None:
    tid, cap = _start_paid_task(client)
    bad = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/get",
            "params": {"id": tid},
        },
    )
    assert bad.json().get("error", {}).get("code") == -32003

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


def test_tasks_get_wrong_capability_rejected(client: TestClient) -> None:
    tid, _ = _start_paid_task(client)
    resp = client.post(
        "/a2a",
        headers={"X-A2A-Task-Capability": "wrong-token"},
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/get",
            "params": {"id": tid},
        },
    )
    assert resp.json().get("error", {}).get("code") == -32003


def test_tasks_cancel_requires_capability(client: TestClient) -> None:
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
    cap = send.json()["result"]["capabilityToken"]

    denied = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/cancel",
            "params": {"id": task_id},
        },
    )
    assert denied.json().get("error", {}).get("code") == -32003

    ok = client.post(
        "/a2a",
        headers={"X-A2A-Task-Capability": cap},
        json={
            "jsonrpc": "2.0",
            "id": "3",
            "method": "tasks/cancel",
            "params": {"id": task_id, "capabilityToken": cap},
        },
    )
    assert ok.json()["result"]["status"]["state"] == "canceled"


def test_cross_client_id_blocked_on_get(client: TestClient) -> None:
    tid, cap = _start_paid_task(client, client_id="owner-1")
    resp = client.post(
        "/a2a",
        headers={
            "X-A2A-Client-Id": "intruder",
            "X-A2A-Task-Capability": cap,
        },
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/get",
            "params": {"id": tid},
        },
    )
    assert resp.json().get("error", {}).get("code") == -32003

    ok = client.post(
        "/a2a",
        headers={
            "X-A2A-Client-Id": "owner-1",
            "X-A2A-Task-Capability": cap,
        },
        json={
            "jsonrpc": "2.0",
            "id": "3",
            "method": "tasks/get",
            "params": {"id": tid},
        },
    )
    assert ok.status_code == 200
    assert ok.json()["result"]["id"] == tid


def test_free_catalog_happy_path_with_capability(client: TestClient) -> None:
    send = client.post(
        "/a2a",
        headers={"X-A2A-Client-Id": "free-client"},
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
    task = send.json()["result"]
    tid = task["id"]
    cap = task["capabilityToken"]
    got = client.post(
        "/a2a",
        headers={
            "X-A2A-Client-Id": "free-client",
            "X-A2A-Task-Capability": cap,
        },
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tasks/get",
            "params": {"id": tid},
        },
    )
    assert got.json()["result"]["status"]["state"] == "completed"


def test_payment_continuation_requires_capability_meta(client: TestClient) -> None:
    from app.a2a_rpc import META_PAYLOAD, META_STATUS

    tid, cap = _start_paid_task(client)
    body = {
        "x402Version": 2,
        "payload": {"signature": "0x", "authorization": {}},
        "accepted": {"payTo": "0x" + "11" * 20},
    }
    missing = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "p1",
            "method": "message/send",
            "params": {
                "message": {
                    "taskId": tid,
                    "metadata": {
                        META_STATUS: "payment-submitted",
                        META_PAYLOAD: body,
                    },
                }
            },
        },
    )
    assert missing.json().get("error", {}).get("code") == -32003

    ok = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "p2",
            "method": "message/send",
            "params": {
                "message": {
                    "taskId": tid,
                    "metadata": {
                        META_STATUS: "payment-submitted",
                        META_PAYLOAD: body,
                        "x402.task.capability": cap,
                    },
                }
            },
        },
    )
    assert ok.status_code == 200
    out = ok.json()["result"]
    assert out["id"] == tid
    assert "error" not in ok.json()
