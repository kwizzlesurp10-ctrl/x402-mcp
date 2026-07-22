"""SWARM_ENABLED gates the buyer role — and only the buyer role.

The flag was declared in config, set to false in render.yaml with a comment
about seller-only posture, and read by nothing. The only thing actually stopping
a public box from spending was the absence of a wallet key.

The dangerous way to fix that is to gate too much: the purchase endpoint and the
read-only views are how customers buy and how you watch the books, and switching
them off with the buyer role would take the storefront's revenue with it.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.swarm import orchestrator
from app.swarm.orchestrator import SwarmDisabledError, require_swarm_enabled

client = TestClient(app)


@pytest.fixture
def swarm_off(monkeypatch):
    monkeypatch.setattr(settings, "swarm_enabled", False)
    monkeypatch.setattr(settings, "dashboard_actions", True)


@pytest.fixture
def swarm_on(monkeypatch):
    monkeypatch.setattr(settings, "swarm_enabled", True)
    monkeypatch.setattr(settings, "dashboard_actions", True)


def test_the_chokepoint_refuses_when_disabled(swarm_off) -> None:
    with pytest.raises(SwarmDisabledError):
        require_swarm_enabled()


def test_the_chokepoint_allows_when_enabled(swarm_on) -> None:
    require_swarm_enabled()  # must not raise


@pytest.mark.asyncio
async def test_the_orchestrator_itself_refuses(swarm_off) -> None:
    """Enforced at the orchestrator so a future caller cannot bypass the flag."""
    with pytest.raises(SwarmDisabledError):
        await orchestrator.run_swarm_research("anything", "agent-1")


def test_http_swarm_run_is_403_when_disabled(swarm_off) -> None:
    response = client.post("/swarm/run", json={"topic": "base gas"})

    assert response.status_code == 403
    assert "SWARM_ENABLED" in response.json()["detail"]


@pytest.mark.asyncio
async def test_the_mcp_tool_refuses_without_burning_quota(swarm_off) -> None:
    from app import mcp_server

    raw = await mcp_server.run_swarm_research(topic="base gas")
    payload = json.loads(raw)

    assert payload["data"] is None
    assert "SWARM_ENABLED" in payload["error"]
    # meta is None because the call never reached the quota consumer.
    assert payload["meta"] is None


# --- the selling side must be untouched ---------------------------------------


def test_selling_still_works_with_the_buyer_role_off(swarm_off) -> None:
    """The purchase endpoint is revenue; gating it with the buyer role would
    silently switch off the storefront."""
    response = client.get("/swarm/products/does-not-exist/purchase")

    # 404 (unknown product), NOT 403 — the route is still open for business.
    assert response.status_code == 404


def test_read_only_swarm_views_still_work(swarm_off) -> None:
    for path in ("/swarm/products", "/swarm/revenue", "/swarm/runs"):
        assert client.get(path).status_code == 200, path
