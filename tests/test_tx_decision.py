"""Per-transaction decision endpoint — the loop-resident tier of the Pulse.

The decision logic is pure (report in, decision out), so the matrix of verdict x
urgency is tested without any network. The route tests cover the same x402 wire
behaviour as /mn/property-check: 402 without a signature, 422 on bad input, and
demand counting with the self-traffic exclusion.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import demand, redis_client, tx_decision
from app.config import settings
from app.main import app

client = TestClient(app)


def _report(verdict="SETTLE_NOW", trend="flat", base_gwei=0.005, tip_gwei=0.001):
    return {
        "generated_at": "2026-07-22T08:00:00+00:00",
        "latest_block": 48941850,
        "eth_price_usd": 3000.0,
        "chain": {"name": "Base mainnet", "network": "eip155:8453"},
        "network": {"block_time_s": 2.0, "tps_est": 30.0},
        "fees": {
            "base_fee_gwei": base_gwei,
            "priority_fee_gwei": tip_gwei,
            "next_base_fee_gwei": base_gwei * 1.05,
            "next_base_fee_change_pct": 5.0,
        },
        "utilization": {"now_pct": 40.0, "avg_pct": 38.0, "trend": trend, "headroom_x": 2.5},
        "assessment": {
            "congestion": "comfortable",
            "verdict": verdict,
            "rationale": "why",
            "window": "stable",
        },
    }


# ---- decision matrix ----------------------------------------------------------


def test_flexible_only_submits_on_settle_now() -> None:
    assert tx_decision.decide(_report("SETTLE_NOW"), 55_000, "flexible")["submit"] is True
    assert tx_decision.decide(_report("SETTLE_SOON"), 55_000, "flexible")["submit"] is False
    assert tx_decision.decide(_report("HOLD_IF_FLEXIBLE"), 55_000, "flexible")["submit"] is False


def test_soon_submits_unless_holding_is_free() -> None:
    assert tx_decision.decide(_report("SETTLE_SOON"), 55_000, "soon")["submit"] is True
    assert tx_decision.decide(_report("HOLD_IF_FLEXIBLE"), 55_000, "soon")["submit"] is False


def test_now_always_submits_with_a_fee() -> None:
    """urgency=now means the caller already decided; our job is only the fee."""
    d = tx_decision.decide(_report("HOLD_IF_FLEXIBLE"), 55_000, "now")

    assert d["submit"] is True
    assert d["recheck_in_s"] is None
    assert d["fee"]["max_fee_per_gas_gwei"] > 0


def test_wait_advice_names_a_recheck_not_a_prediction() -> None:
    d = tx_decision.decide(_report("HOLD_IF_FLEXIBLE", trend="rising"), 55_000, "flexible")

    assert d["submit"] is False
    assert d["recheck_in_s"] == 12  # 6 blocks * 2s: when a re-check turns informative
    # A falling trend warrants looking again sooner.
    d2 = tx_decision.decide(_report("HOLD_IF_FLEXIBLE", trend="falling"), 55_000, "flexible")
    assert d2["recheck_in_s"] == 6


def test_fee_sizing_follows_eip1559_wallet_practice() -> None:
    """max_fee = 2*base + tip rides out full blocks; cost uses current base."""
    d = tx_decision.decide(_report(base_gwei=0.01, tip_gwei=0.002), 55_000, "now")

    assert d["fee"]["max_fee_per_gas_gwei"] == pytest.approx(0.022)
    # expected cost burns base+tip, never the max: 55000 * 0.012 gwei
    assert d["estimated_cost"]["eth"] == pytest.approx(55_000 * 0.012 / 1e9)
    assert d["estimated_cost"]["usd"] == pytest.approx(55_000 * 0.012 / 1e9 * 3000, rel=1e-3)


def test_response_carries_its_own_freshness() -> None:
    d = tx_decision.decide(_report(), 55_000, "flexible")

    assert d["as_of_block"] == 48941850
    assert d["as_of"]  # ISO stamp — the caller judges staleness, we do not hide it


# ---- the paid route -----------------------------------------------------------


@pytest.fixture(autouse=True)
def _seller(monkeypatch):
    monkeypatch.setattr(settings, "x402_pay_to_address", "0xabc")
    monkeypatch.setattr(demand, "_memory", demand.Counter())
    monkeypatch.setattr(demand, "_memory_last", {})
    monkeypatch.setattr(redis_client, "client", None)


def test_unpaid_request_gets_a_402_with_the_challenge(monkeypatch) -> None:
    monkeypatch.setattr(
        tx_decision, "build_payment_required_header", lambda: "aGRy"
    )

    response = client.get("/base/tx-decision?gas=usdc&urgency=flexible")

    assert response.status_code == 402
    assert response.headers["PAYMENT-REQUIRED"] == "aGRy"
    body = response.json()
    assert body["price"] == settings.tx_decision_price
    assert "submit" in body["description"].lower() or "fee" in body["description"].lower()


def test_the_402_counts_demand_but_not_self_traffic(monkeypatch) -> None:
    monkeypatch.setattr(tx_decision, "build_payment_required_header", lambda: "aGRy")

    client.get("/base/tx-decision")
    client.get("/base/tx-decision", headers={"X-Demand-Ignore": "monitor"})

    assert demand.challenges().get("base-tx-decision") == 1


def test_gas_presets_and_custom_integers(monkeypatch) -> None:
    monkeypatch.setattr(tx_decision, "build_payment_required_header", lambda: "aGRy")

    assert client.get("/base/tx-decision?gas=x402").status_code == 402  # preset ok
    assert client.get("/base/tx-decision?gas=150000").status_code == 402  # integer ok
    assert client.get("/base/tx-decision?gas=banana").status_code == 422
    assert client.get("/base/tx-decision?gas=5").status_code == 422  # below intrinsic 21000


def test_bad_urgency_is_rejected_before_any_payment_logic() -> None:
    response = client.get("/base/tx-decision?urgency=yesterday")

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_urgency"


def test_unconfigured_seller_refuses_rather_than_serving_free(monkeypatch) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", "")

    assert client.get("/base/tx-decision").status_code == 503
