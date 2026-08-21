"""Strategic assessor tests — deterministic scoring + honest human-gates."""

from __future__ import annotations

from app.swarm import assessor


def test_assessment_shape_and_ordering():
    a = assessor.assess()
    for key in ("signals", "profit_routes", "recommended_route", "backlog",
                "immediate_technical_actions", "human_gates", "scoring_model"):
        assert key in a

    routes = a["profit_routes"]
    # scored, sorted descending
    scores = [r["priority_score"] for r in routes]
    assert scores == sorted(scores, reverse=True)
    # recommended route is the top-scored one
    assert a["recommended_route"]["id"] == routes[0]["id"]


def test_weights_sum_to_one():
    assert round(sum(assessor.WEIGHTS.values()), 6) == 1.0


def test_growth_functions_are_human_gated():
    a = assessor.assess()
    gated = {b["charter"] for b in a["backlog"] if b["human_gated"]}
    # outreach and advertising must never be auto-run
    assert "outreach" in gated
    assert "advertising" in gated
    # immediate technical actions must contain no human-gated items
    tech_charters = {t["charter"] for t in a["immediate_technical_actions"]}
    assert tech_charters.isdisjoint({"outreach", "advertising", "content_seo"})


def test_signals_are_real():
    from app.tools_registry import TOOL_COUNT

    s = assessor.gather_signals()
    assert s["mcp_tools"] == TOOL_COUNT
    assert s["app_modules"] > 0 and s["test_files"] > 0


def test_feedback_loop_marks_completed_charters():
    """The assessor detects completed technical work from code (feedback loop)."""
    a = assessor.assess()
    # Security KeyProvider + Solana multi-chain are shipped -> detected as done.
    assert a["signals"]["security_keyprovider"] is True
    assert a["signals"]["multichain_solana"] is True
    done = {b["charter"] for b in a["backlog"] if b["status"] == "done"}
    assert {"security_hardener", "multichain"} <= done
    # Their completion unblocks the Hosted SaaS route (no unmet prereqs).
    saas = next(r for r in a["profit_routes"] if r["id"] == "hosted_saas")
    assert saas["blocked_by"] == []


def test_product_focus_realignment():
    """PRODUCT-FOCUS.md: invest in mn, cost-basis shape; demote Pulse synthesis.

    Unfrozen 2026-08-04. Guard against the assessor re-recommending free-RPC
    synthesis as the top profit route after measured ~0% external conversion.
    """
    a = assessor.assess()
    by_id = {r["id"]: r for r in a["profit_routes"]}
    assert {"mn_invest", "cost_basis_resale", "synthesis_publisher"} <= by_id.keys()
    assert "mn_hold" not in by_id

    # Invest + cost-basis shape outrank demoted free-RPC synthesis.
    assert by_id["mn_invest"]["priority_score"] > by_id["synthesis_publisher"]["priority_score"]
    assert by_id["cost_basis_resale"]["priority_score"] > by_id["synthesis_publisher"]["priority_score"]

    # Never recommend Pulse/tx-decision synthesis as the top route.
    assert a["recommended_route"]["id"] != "synthesis_publisher"
    # With seller_ready true (pay-to configured in tests/CI), mn invest is top.
    if a["signals"]["seller_ready"]:
        assert a["recommended_route"]["id"] == "mn_invest"
