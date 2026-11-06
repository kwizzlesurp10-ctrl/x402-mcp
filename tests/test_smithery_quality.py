"""Smithery 100/100 quality dimensions — tools, params, annotations, metadata."""

from __future__ import annotations

import json
from pathlib import Path

from app.mcp_server import INSTRUCTIONS, mcp
from app.tools_registry import EXPECTED_TOOL_NAMES, TOOL_COUNT

ROOT = Path(__file__).resolve().parents[1]


def test_smithery_artifacts_retired() -> None:
    """Pre-Oct 31 cutover: smithery proxy artifacts are permanently retired."""
    assert not (ROOT / "smithery.yaml").exists()
    assert not (ROOT / "smithery.remote-config.json").exists()


def test_every_tool_uses_dot_notation() -> None:
    assert len(EXPECTED_TOOL_NAMES) == TOOL_COUNT
    for name in EXPECTED_TOOL_NAMES:
        assert "." in name, name
        domain, action = name.split(".", 1)
        assert domain and action, name
        assert not name.startswith("mailrail."), name


def test_instructions_name_dotted_tools() -> None:
    assert "x402.discover" in INSTRUCTIONS
    assert "city.list" in INSTRUCTIONS
    assert "commerce.pro_requirements" in INSTRUCTIONS


async def test_tools_have_annotations_and_param_descriptions() -> None:
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES
    for tool in tools:
        assert tool.description and len(tool.description) > 40, tool.name
        assert tool.annotations is not None, tool.name
        assert tool.annotations.readOnlyHint is not None, tool.name
        assert tool.annotations.destructiveHint is not None, tool.name
        assert tool.annotations.openWorldHint is not None, tool.name
        props = (tool.inputSchema or {}).get("properties") or {}
        for pname, spec in props.items():
            assert spec.get("description"), f"{tool.name}.{pname}"


def test_server_card_has_annotations_and_param_descriptions() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    data = client.get("/.well-known/mcp/server-card.json").json()
    tools = data["tools"]
    assert tools
    names = {t["name"] for t in tools}
    assert names == EXPECTED_TOOL_NAMES
    for tool in tools:
        assert "." in tool["name"]
        assert not tool["name"].startswith("mailrail.")
        ann = tool.get("annotations")
        assert isinstance(ann, dict), tool["name"]
        assert ann.get("readOnlyHint") is not None, tool["name"]
        assert ann.get("destructiveHint") is not None, tool["name"]
        assert ann.get("openWorldHint") is not None, tool["name"]
        props = (tool.get("inputSchema") or {}).get("properties") or {}
        for pname, spec in props.items():
            assert spec.get("description"), f"{tool['name']}.{pname}"
        # city.check / x402.policy_check are unstructured (PaymentRequired CallToolResult
        # bypasses {result: str} schema).
        if tool["name"] not in ("city.check", "x402.policy_check"):
            assert "outputSchema" in tool, tool["name"]
    prompt_names = {p["name"] for p in data["prompts"]}
    assert "x402.sell_api" in prompt_names
    assert isinstance(data["prompts"], list) and data["prompts"]
    assert isinstance(data["resources"], list) and data["resources"]
    assert data["configSchema"].get("required", []) == []


async def test_prompts_and_resources_are_registered() -> None:
    prompts = await mcp.list_prompts()
    resources = await mcp.list_resources()
    prompt_names = {p.name for p in prompts}
    resource_names = {r.name for r in resources}
    assert "x402.buy_paid_api" in prompt_names
    assert "x402.sell_api" in prompt_names
    assert "city.compliance_path" in prompt_names
    assert "x402.instructions" in resource_names
    assert "x402.catalog" in resource_names
    for prompt in prompts:
        assert prompt.description
        for arg in prompt.arguments or []:
            if arg.name:
                assert arg.description, f"{prompt.name}.{arg.name}"
