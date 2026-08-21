"""README accuracy — tool count matches shipped manifest."""

from pathlib import Path

import pytest

from app.tools_registry import EXPECTED_TOOL_NAMES, TOOL_COUNT

EXPECTED_TOOLS = EXPECTED_TOOL_NAMES

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def test_readme_features_says_tool_count() -> None:
    text = README.read_text(encoding="utf-8")
    assert f"{TOOL_COUNT} MCP tools" in text
    # Guard against stale adjacent counts left after a registry bump.
    for n in range(TOOL_COUNT - 3, TOOL_COUNT + 3):
        if n == TOOL_COUNT or n < 1:
            continue
        assert f"{n} MCP tools" not in text


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS))
def test_readme_lists_each_tool(tool_name: str) -> None:
    text = README.read_text(encoding="utf-8")
    assert f"`{tool_name}`" in text