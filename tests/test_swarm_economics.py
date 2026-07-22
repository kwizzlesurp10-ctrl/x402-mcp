"""A swarm cycle spends nothing by default — Pulse economics, not composite economics.

Measured composite runs booked a real cost basis and then did not sell (LTV:CAC
1.35 against a 3.0 target). The Pulse product reads free Base RPC and spot data,
so its cost basis is 0: unsold inventory is free to hold and any sale is
essentially all margin. Defaulting the swarm to free synthesis moves it onto
those economics; buying is now something you opt into.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.swarm import orchestrator, publisher
from app.swarm.models import CompositeProduct


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(settings, "swarm_enabled", True)


@pytest.fixture
def synthesized(monkeypatch) -> list[str]:
    """Stub the free-input publisher; record that it was the path taken."""
    calls: list[str] = []

    async def _fake_publish(agent_id, price_usdc=None, product_id=None):
        calls.append(agent_id)
        return CompositeProduct(
            product_id="synth-1",
            topic="Base Network Pulse @ block 1",
            cost_basis_usdc=0.0,  # free inputs — the whole point
            price_usdc=0.05,
            markup=0.0,
            network="eip155:8453",
            sources=["https://mainnet.base.org"],
            report="report",
            status="listed",
            seller_agent_id=agent_id,
            seller_requirements={"payment_required_header": "hdr"},
        )

    monkeypatch.setattr(publisher, "publish_pulse_product", _fake_publish)
    return calls


@pytest.fixture
def explode_on_buy(monkeypatch):
    """Any attempt to reach the buy path is a failure of the default."""

    async def _boom(*args, **kwargs):
        raise AssertionError("the default cycle must not scout or buy")

    monkeypatch.setattr(orchestrator.roles, "scout", _boom)
    monkeypatch.setattr(orchestrator.roles, "treasurer_buy", _boom)


@pytest.mark.asyncio
async def test_a_default_cycle_costs_nothing(
    monkeypatch, synthesized, explode_on_buy
) -> None:
    monkeypatch.setattr(settings, "swarm_allow_paid_inputs", False)

    run = await orchestrator.run_swarm_research("base gas", agent_id="agent-1")

    assert run["status"] == "listed"
    assert run["product"]["cost_basis_usdc"] == 0.0
    assert run["purchases"] == []
    assert synthesized == ["agent-1"]


@pytest.mark.asyncio
async def test_the_caller_can_override_the_config_default(
    monkeypatch, synthesized, explode_on_buy
) -> None:
    """Config says buying is allowed; this call explicitly declines to spend."""
    monkeypatch.setattr(settings, "swarm_allow_paid_inputs", True)

    run = await orchestrator.run_swarm_research(
        "base gas", agent_id="agent-2", allow_paid_inputs=False
    )

    assert run["product"]["cost_basis_usdc"] == 0.0
    assert synthesized == ["agent-2"]


@pytest.mark.asyncio
async def test_opting_in_reaches_the_buy_path(monkeypatch, synthesized) -> None:
    """Buying still works when asked for — this is a default, not a removal."""
    reached = []

    async def _scout(run, topic, cap):
        reached.append(topic)
        return []  # empty -> the cycle fails, which is fine; we only assert the route

    monkeypatch.setattr(orchestrator.roles, "scout", _scout)

    run = await orchestrator.run_swarm_research(
        "base gas", agent_id="agent-3", allow_paid_inputs=True
    )

    assert reached == ["base gas"]
    assert synthesized == []  # no silent fallback to synthesis
    assert run["status"] == "failed"


@pytest.mark.asyncio
async def test_a_failed_paid_run_is_not_papered_over(monkeypatch, synthesized) -> None:
    """A caller who opted into spending gets a real failure, not a substitute."""

    async def _scout(run, topic, cap):
        raise RuntimeError("discovery unreachable")

    monkeypatch.setattr(orchestrator.roles, "scout", _scout)

    run = await orchestrator.run_swarm_research(
        "base gas", agent_id="agent-4", allow_paid_inputs=True
    )

    assert run["status"] == "failed"
    assert "discovery unreachable" in run["error"]
    assert synthesized == []
