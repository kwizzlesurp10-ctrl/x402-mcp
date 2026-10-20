"""Agent-ops static artifacts from x402-agent-ops package."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

AGENT_NAMES = ("scout", "warden", "treasurer", "archivist", "merchant")


def test_agent_files_exist() -> None:
    for name in AGENT_NAMES:
        path = ROOT / ".claude" / "agents" / f"x402-{name}.md"
        assert path.exists(), f"missing {path}"


def test_ledger_policy_exists() -> None:
    assert (ROOT / "ledger" / "policy.json").exists()


def test_docs_and_mcp_example() -> None:
    assert (ROOT / "docs" / "agent-ops.md").exists()
    assert (ROOT / "docs" / "UI-HANDOFF.md").exists()
    assert (ROOT / ".mcp.json.example").exists()


def test_merchant_has_no_stripe_references() -> None:
    text = (ROOT / ".claude" / "agents" / "x402-merchant.md").read_text(
        encoding="utf-8"
    )
    assert "stripe" not in text.lower()