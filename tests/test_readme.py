"""README accuracy — tool count matches shipped manifest."""

from pathlib import Path

import pytest

from app.tools_registry import EXPECTED_TOOL_NAMES

EXPECTED_TOOLS = EXPECTED_TOOL_NAMES

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def test_readme_features_says_fifteen_tools() -> None:
    text = README.read_text(encoding="utf-8")
    assert "15 MCP tools" in text
    assert "14 MCP tools" not in text


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS))
def test_readme_lists_each_tool(tool_name: str) -> None:
    text = README.read_text(encoding="utf-8")
    assert f"`{tool_name}`" in text