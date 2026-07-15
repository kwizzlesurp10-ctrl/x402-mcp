"""Swarm Agency: buy → compose → list → settle, with mocked x402 rails.

Follows repo conventions: async direct-invocation, monkeypatch collaborators,
tmp_path ledger redirect (see tests/test_ops.py).
"""

from __future__ import annotations

import json

import pytest

from app import ledger_io, x402_services
from app.config import settings
from app.swarm import orchestrator
from app.swarm.registry import swarm_registry

TESTNET = "eip155:84532"

_POLICY = {
    "max_price_per_call_usdc": 0.05,
    "daily_cap_usdc": 0.50,
    "monthly_cap_usdc": 3.00,
    "allowed_networks_mainnet": ["eip155:8453"],
    "testnet_networks": [TESTNET],
    "domain_denylist": [],
    "domain_allowlist": [],
    "require_testnet_first": True,
    "receive_wallet": "0xSELLER",
}


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    (ledger_dir / "policy.json").write_text(json.dumps(_POLICY), encoding="utf-8")
    monkeypatch.setattr(ledger_io, "LEDGER", ledger_dir)
    return ledger_dir


def _fake_service(url: str, atomic: int, network: str = TESTNET) -> dict:
    return {"resource": url, "accepts": [{"amount": atomic, "network": network}]}


@pytest.fixture
def rails(monkeypatch):
    """Mock buy + sell so no real chain calls happen."""

    async def fake_discover(params):
        return {
            "services": [
                _fake_service("https://svc.test/alpha", 10_000),  # $0.01
                _fake_service("https://svc.test/beta", 20_000),  # $0.02
            ],
            "count": 2,
        }

    async def fake_pay(params):
        return {
            "status_code": 200,
            "body": f"data from {params.url}",
            "payment_settled": True,
            "payment_settlement": {
                "success": True,
                "transaction": "0xabc123",
                "network": TESTNET,
            },
        }

    def fake_seller(params):
        return {
            "requirements": [{"scheme": "exact", "network": params.network}],
            "pay_to": "0xSELLER",
            "price": params.price,
            "network": params.network,
        }

    monkeypatch.setattr(x402_services, "discover_services", fake_discover)
    monkeypatch.setattr(x402_services, "pay_and_fetch", fake_pay)
    monkeypatch.setattr(x402_services, "build_seller_requirements", fake_seller)
    monkeypatch.setattr(settings, "swarm_markup", 3.0)
    monkeypatch.setattr(settings, "swarm_min_price_usdc", 0.01)
    monkeypatch.setattr(settings, "swarm_max_upstream_calls", 3)


@pytest.mark.asyncio
async def test_full_loop_lists_priced_composite(ledger, rails):
    run = await orchestrator.run_swarm_research("zk rollups", agent_id="agent-1")

    assert run["status"] == "listed", run.get("error")
    assert len(run["purchases"]) == 2
    product = run["product"]
    # cost basis = 0.01 + 0.02 = 0.03; price = 0.03 * 3 markup = 0.09
    assert product["cost_basis_usdc"] == pytest.approx(0.03)
    assert product["price_usdc"] == pytest.approx(0.09)
    assert product["status"] == "listed"
    assert product["seller_requirements"]["pay_to"] == "0xSELLER"

    # spend ledger recorded both buys as cost basis
    spend = ledger_io.read_ledger_rows("spend")
    assert len(spend) == 2
    assert sum(r["amount_usdc"] for r in spend) == pytest.approx(0.03)
    assert all(r["settled"] for r in spend)


@pytest.mark.asyncio
async def test_warden_vetoes_over_cap(ledger, monkeypatch):
    async def fake_discover(params):
        return {"services": [_fake_service("https://svc.test/pricey", 200_000)]}  # $0.20

    monkeypatch.setattr(x402_services, "discover_services", fake_discover)

    run = await orchestrator.run_swarm_research("expensive", agent_id="agent-2")

    assert run["status"] == "failed"
    assert "vetoed" in (run["error"] or "")
    assert run["purchases"] == []
    assert any("max_price_per_call" in v["reason"] for v in run["vetoes"])


@pytest.mark.asyncio
async def test_settle_sale_records_revenue(ledger, rails, monkeypatch):
    run = await orchestrator.run_swarm_research("defi", agent_id="agent-3")
    product_id = run["product"]["product_id"]
    assert swarm_registry.get_product(product_id) is not None

    async def fake_settle(params):
        return {
            "is_valid": True,
            "invalid_reason": None,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0xdeadbeef"},
        }

    monkeypatch.setattr(x402_services, "_verify_and_settle_payment", fake_settle)

    result = await orchestrator.settle_composite_sale(
        product_id, "c2ln", "cmVx", buyer_agent_id="buyer-1"
    )

    assert result["sold"] is True
    assert result["revenue_usdc"] == pytest.approx(0.09)
    assert result["margin_usdc"] == pytest.approx(0.06)  # 0.09 - 0.03

    revenue = ledger_io.read_ledger_rows("revenue")
    assert len(revenue) == 1
    assert revenue[0]["amount_usdc"] == pytest.approx(0.09)
    assert revenue[0]["product_id"] == product_id


@pytest.mark.asyncio
async def test_sovereign_optimizes_to_target_ltv_cac(ledger, rails):
    run = await orchestrator.run_swarm_research("defi", "agent-sra")

    assert run["status"] == "listed", run.get("error")
    product = run["product"]
    # cost basis 0.03 -> price 0.09 at target markup 3.0 -> LTV:CAC 3.0
    assert product["ltv_cac_projected"] == pytest.approx(3.0)
    assert product["price_usdc"] == pytest.approx(0.09)


@pytest.mark.asyncio
async def test_revenue_report_reflects_run(ledger, rails):
    await orchestrator.run_swarm_research("defi", "agent-sra")

    from app.swarm import sovereign

    rep = sovereign.build_revenue_report()
    assert rep["total_spend_usdc"] == pytest.approx(0.03)
    assert rep["listed_count"] >= 1
    assert rep["ltv_cac"] is None or rep["ltv_cac"] >= 0
    assert rep["target_ltv_cac"] == 3.0
    assert isinstance(rep["recommendations"], list)


@pytest.mark.asyncio
async def test_revenue_report_after_sale(ledger, rails, monkeypatch):
    run = await orchestrator.run_swarm_research("defi", "agent-sra")
    product_id = run["product"]["product_id"]

    async def fake_settle(params):
        return {
            "is_valid": True,
            "invalid_reason": None,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0xfeed"},
        }

    monkeypatch.setattr(x402_services, "_verify_and_settle_payment", fake_settle)

    await orchestrator.settle_composite_sale(
        product_id, "c2ln", "cmVx", buyer_agent_id="buyer-x"
    )

    from app.swarm import sovereign

    rep = sovereign.build_revenue_report()
    assert rep["sold_count"] >= 1
    assert rep["total_revenue_usdc"] == pytest.approx(0.09)
