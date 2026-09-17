"""README accuracy and synchronization test suite.

Verifies:
1. Exact MCP tool count (20 MCP tools) and individual tool listing.
2. Official Smithery badge and Quickstart 1-click installation commands.
3. A2A Protocol v1.0 Agent ID Card & Machine Identity documentation.
4. Complete MCP Prompts documentation (4 prompts).
5. Complete MCP Resources documentation (4 resources).
6. Parameter specifications and sample AI agent interaction workflows.
"""

from pathlib import Path

import pytest

from app.tools_registry import EXPECTED_TOOL_NAMES, TOOL_COUNT

EXPECTED_TOOLS = EXPECTED_TOOL_NAMES

EXPECTED_PROMPTS = (
    "onboarding_flow",
    "x402_tool_selector",
    "generate_quote",
    "troubleshoot_payment",
)

EXPECTED_RESOURCES = (
    "x402://agent-card",
    "x402://server-card",
    "x402://tools-manifest",
    "x402://pricing-table",
)

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def test_readme_features_says_tool_count() -> None:
    """Ensure tool count in README matches canonical TOOL_COUNT."""
    text = README.read_text(encoding="utf-8")
    assert f"{TOOL_COUNT} MCP tools" in text
    # Guard against stale adjacent counts left after a registry bump.
    for n in range(TOOL_COUNT - 3, TOOL_COUNT + 3):
        if n == TOOL_COUNT or n < 1:
            continue
        assert f"{n} MCP tools" not in text


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS))
def test_readme_lists_each_tool(tool_name: str) -> None:
    """Ensure every canonical tool name is documented with backticks."""
    text = README.read_text(encoding="utf-8")
    assert f"`{tool_name}`" in text


def test_readme_smithery_badge_present() -> None:
    """Verify official Smithery badge is present."""
    text = README.read_text(encoding="utf-8")
    assert (
        "[![smithery badge](https://smithery.ai/badge/kwizzlesurp10/x402-mcp)](https://smithery.ai/server/kwizzlesurp10/x402-mcp)"
        in text
    )


def test_readme_24klabs_badge_present() -> None:
    """Verify the 24K Labs listing badge is present."""
    text = README.read_text(encoding="utf-8")
    assert "https://24klabs.ai/listing/us-city-open-data-compliance-network" in text
    assert (
        "https://24klabs.ai/badge.svg?resource=https%3A%2F%2Fx402-mcp.onrender.com%2F.well-known%2Fx402"
        in text
    )


def test_readme_quickstart_smithery_cli_install() -> None:
    """Verify 1-click Smithery CLI installation commands for Claude, Cursor, and Windsurf."""
    text = README.read_text(encoding="utf-8")
    assert "npx -y @smithery/cli install kwizzlesurp10/x402-mcp --client claude" in text
    assert "npx -y @smithery/cli install kwizzlesurp10/x402-mcp --client cursor" in text
    assert "npx -y @smithery/cli install kwizzlesurp10/x402-mcp --client windsurf" in text


def test_readme_agent_id_card_section() -> None:
    """Verify Agent ID Card and A2A Protocol v1.0 section."""
    text = README.read_text(encoding="utf-8")
    assert "Agent ID Cards & Machine Identity" in text
    assert "Agent-to-Agent (A2A) Protocol v1.0" in text
    assert "`x402.agent_card`" in text
    assert "`x402://agent-card`" in text
    assert "`agent_id`" in text


@pytest.mark.parametrize("prompt_name", sorted(EXPECTED_PROMPTS))
def test_readme_lists_each_prompt(prompt_name: str) -> None:
    """Verify all 4 MCP prompts are documented."""
    text = README.read_text(encoding="utf-8")
    assert f"`{prompt_name}`" in text


@pytest.mark.parametrize("resource_uri", sorted(EXPECTED_RESOURCES))
def test_readme_lists_each_resource(resource_uri: str) -> None:
    """Verify all 4 MCP resources are documented."""
    text = README.read_text(encoding="utf-8")
    assert f"`{resource_uri}`" in text


def test_readme_sample_agent_queries_present() -> None:
    """Verify realistic sample AI agent prompt workflows are provided."""
    text = README.read_text(encoding="utf-8")
    assert "Sample AI Agent Queries & Interactions" in text
    assert "Real Estate Compliance Workflow" in text
    assert "Base Network Gas & Settlement Timing" in text
    assert "Service Discovery & Protected API Consumption" in text
    assert "Seller API Monetization" in text