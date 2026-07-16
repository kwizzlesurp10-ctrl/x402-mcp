"""Strategic Assessment & Profit-Route Optimizer — the swarm's strategic core.

Grounds the "Production & Profit Swarm" in reality: gathers real repo/system
signals, scores profit routes with a transparent weighted model (not marketing
numbers), and emits a prioritized backlog mapped to the operating charters —
with growth/outreach/financial items explicitly HUMAN-GATED, never auto-run.

Deliberately honest: every score is computed from declared, inspectable inputs;
nothing here executes outreach, ads, or makes financial claims.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.tools_registry import TOOL_COUNT

ROOT = Path(__file__).resolve().parents[2]

# Transparent scoring weights (sum = 1.0). Higher route score = do sooner.
WEIGHTS = {
    "speed_to_revenue": 0.30,  # 1 = fast
    "capital_efficiency": 0.20,  # 1 = cheap/low-risk
    "tool_leverage": 0.20,  # 1 = strongly enabled by tools we have
    "defensibility": 0.15,  # 1 = durable moat
    "impact": 0.15,  # 1 = large 6-mo impact
}


def _sh(*args: str) -> str:
    try:
        return subprocess.run(
            args, cwd=ROOT, capture_output=True, text=True, timeout=15
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def gather_signals() -> dict[str, Any]:
    """Real, inspectable facts about the repo and running system."""
    commits = _sh("git", "-C", str(ROOT), "rev-list", "--count", "HEAD")
    head = _sh("git", "-C", str(ROOT), "rev-parse", "--short", "HEAD")
    app_modules = len(list((ROOT / "app").glob("*.py"))) + len(
        list((ROOT / "app" / "swarm").glob("*.py"))
    )
    tests = len(list((ROOT / "tests").glob("test_*.py")))
    return {
        "commits": int(commits) if commits.isdigit() else None,
        "head": head or None,
        "mcp_tools": TOOL_COUNT,
        "app_modules": app_modules,
        "test_files": tests,
        "settlement_mainnet": bool(settings.cdp_api_key_id and settings.cdp_api_key_secret),
        "seller_ready": bool(settings.x402_pay_to_address),
        "has_synthesis_product": (ROOT / "app" / "pulse.py").exists(),
        "public_storefront": (ROOT / "docs" / "SELLER-STOREFRONT.md").exists(),
    }


# ---- Profit routes (attributes are the inspectable inputs, 0..1) -------------
# Each route carries the attribute estimates AND real prerequisites; the score
# is COMPUTED from WEIGHTS, and blocked-by-prereqs routes are demoted.
_ROUTES: list[dict[str, Any]] = [
    {
        "id": "synthesis_publisher",
        "name": "Synthesis publisher (Base Network Pulse)",
        "attrs": {"speed_to_revenue": 0.9, "capital_efficiency": 0.95,
                  "tool_leverage": 0.9, "defensibility": 0.5, "impact": 0.6},
        "prereqs": ["seller_ready", "settlement_mainnet"],
        "status_note": "Built & live: real data, priced, 402-payable. Needs external buyers.",
        "next_action": "Publish seller storefront publicly; list where x402 buyers look.",
    },
    {
        "id": "hosted_saas",
        "name": "Hosted SaaS + usage analytics",
        "attrs": {"speed_to_revenue": 0.4, "capital_efficiency": 0.5,
                  "tool_leverage": 0.8, "defensibility": 0.8, "impact": 0.9},
        "prereqs": ["security_keyprovider", "multichain"],
        "status_note": "Highest ceiling; gated on security + multi-chain prerequisites.",
        "next_action": "Land Security KeyProvider + Multi-chain PRs first.",
    },
    {
        "id": "content_flywheel",
        "name": "Content + organic distribution flywheel",
        "attrs": {"speed_to_revenue": 0.5, "capital_efficiency": 0.7,
                  "tool_leverage": 0.7, "defensibility": 0.4, "impact": 0.6},
        "prereqs": [],
        "human_gated": True,
        "status_note": "Recommendations only — content/campaigns are human-executed.",
        "next_action": "Draft 3 demo concepts for human review (no auto-publish).",
    },
    {
        "id": "tech_productionization",
        "name": "Technical productionization + organic GitHub growth",
        "attrs": {"speed_to_revenue": 0.35, "capital_efficiency": 0.9,
                  "tool_leverage": 0.85, "defensibility": 0.5, "impact": 0.5},
        "prereqs": [],
        "status_note": "Close the 12-charter technical backlog; credibility prerequisite.",
        "next_action": "Execute Security, Multi-chain, CI backlog items.",
    },
    {
        "id": "merchant_revshare",
        "name": "Affiliate / merchant revenue share",
        "attrs": {"speed_to_revenue": 0.3, "capital_efficiency": 0.8,
                  "tool_leverage": 0.5, "defensibility": 0.6, "impact": 0.5},
        "prereqs": [],
        "human_gated": True,
        "status_note": "Partnership model — human-gated commercial terms.",
        "next_action": "Map top Bazaar merchants for human-led outreach.",
    },
]


def score_routes(signals: dict[str, Any]) -> list[dict[str, Any]]:
    prereq_state = {
        "seller_ready": signals["seller_ready"],
        "settlement_mainnet": signals["settlement_mainnet"],
        # technical prereqs that are NOT yet done (honest):
        "security_keyprovider": False,
        "multichain": False,
    }
    scored = []
    for r in _ROUTES:
        raw = sum(r["attrs"][k] * w for k, w in WEIGHTS.items()) * 10
        unmet = [p for p in r["prereqs"] if not prereq_state.get(p, False)]
        # Demote by 1.2 points per unmet prerequisite (can't run it yet).
        score = round(max(raw - 1.2 * len(unmet), 0), 1)
        scored.append({
            "id": r["id"],
            "name": r["name"],
            "priority_score": score,
            "raw_score": round(raw, 1),
            "blocked_by": unmet,
            "human_gated": r.get("human_gated", False),
            "status_note": r["status_note"],
            "next_action": r["next_action"],
        })
    scored.sort(key=lambda x: x["priority_score"], reverse=True)
    return scored


# ---- 12-charter backlog with real status ------------------------------------
def build_backlog(signals: dict[str, Any]) -> list[dict[str, Any]]:
    """Map the operating charters to work items with honest, current status."""
    items = [
        ("assessment_optimizer", "Strategic Assessment & Profit-Route Optimizer",
         "active", False, "This module — live scoring + backlog."),
        ("orchestrator", "Orchestrator & state manager",
         "partial", False, "Swarm orchestrator + registry exist; no weekly trigger yet."),
        ("security_hardener", "Security & trust hardener (KeyProvider)",
         "available", False,
         "REAL GAP: EVM_PRIVATE_KEY lives in env. Add pluggable KeyProvider + env "
         "deprecation warning + spend-velocity alerts."),
        ("multichain", "Multi-chain / protocol completer",
         "available", False,
         "REAL GAP: only ExactEvmServerScheme is registered. Wire ExactSvmScheme "
         "(Solana) so marketing matches code."),
        ("code_quality_ci", "Code quality, testing & CI",
         "partial", False, "Strong tests; add CI lint/secret-scan/audit workflow."),
        ("mcp_extender", "MCP compliance & feature extender",
         "partial", False, "Pulse tool shipped; add Resources (catalog) + Prompts (policy)."),
        ("market_intel", "Market intelligence & competitive analyst",
         "human_assisted", False, "Needs web/X access; produces signals for review."),
        ("content_seo", "Positioning, content & SEO engine",
         "human_gated", True, "Content is human-created/approved. Recommendations only."),
        ("outreach", "Outreach, partnerships & community",
         "human_gated", True, "Mass outreach GATED. Assistant drafts, humans send."),
        ("advertising", "Advertising, distribution & acquisition",
         "human_gated", True, "Ad spend GATED. Recommends budgets/experiments only."),
        ("sales_monetization", "Sales, monetization & product owner",
         "partial", True, "Pulse is a priced product; pricing/financial claims human-gated."),
        ("ops_monitoring", "Ops, monitoring, protection & analytics",
         "available", False,
         "Policy caps exist; add runtime spend-anomaly alerts + CDP/Bazaar health checks."),
    ]
    return [
        {
            "charter": cid,
            "title": title,
            "status": status,
            "human_gated": gated,
            "detail": detail,
        }
        for (cid, title, status, gated, detail) in items
    ]


def assess() -> dict[str, Any]:
    """Full strategic assessment: signals + scored routes + backlog + recommendation."""
    signals = gather_signals()
    routes = score_routes(signals)
    backlog = build_backlog(signals)
    top = routes[0]

    # Next technical actions = highest-value non-gated backlog items not yet done.
    tech_next = [
        b for b in backlog
        if b["status"] == "available" and not b["human_gated"]
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "signals": signals,
        "profit_routes": routes,
        "recommended_route": {
            "id": top["id"],
            "name": top["name"],
            "priority_score": top["priority_score"],
            "why": top["status_note"],
            "next_action": top["next_action"],
        },
        "backlog": backlog,
        "immediate_technical_actions": [
            {"charter": b["charter"], "title": b["title"], "detail": b["detail"]}
            for b in tech_next
        ],
        "human_gates": [
            b["title"] for b in backlog if b["human_gated"]
        ],
        "scoring_model": {"weights": WEIGHTS, "note": "route score = Σ(attr×weight)×10, "
                          "minus 1.2 per unmet prerequisite; fully inspectable."},
    }
