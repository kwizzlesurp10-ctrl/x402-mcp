"""Smithery 100/100 quality dimensions — tools, params, annotations, metadata."""

from __future__ import annotations

import json
from pathlib import Path

from app.mcp_server import INSTRUCTIONS, mcp
from app.tools_registry import EXPECTED_TOOL_NAMES, TOOL_COUNT

ROOT = Path(__file__).resolve().parents[1]


def test_smithery_yaml_has_full_metadata() -> None:
    text = (ROOT / "smithery.yaml").read_text(encoding="utf-8")
    for needle in (
        "name: x402-mcp",
        "displayName: \"x402-mcp\"",
        "description:",
        "homepage: \"https://x402-mcp.onrender.com\"",
        "repository: \"https://github.com/kwizzlesurp10-ctrl/x402-mcp\"",
        "license: \"MIT\"",
        "categories:",
        "tags:",
        "startCommand:",
        "X402_PAY_TO_ADDRESS:",
        "EVM_PRIVATE_KEY:",
    ):
        assert needle in text, needle


def test_remote_config_schema_has_no_required_fields() -> None:
    schema = json.loads((ROOT / "smithery.remote-config.json").read_text(encoding="utf-8"))
    assert schema["required"] == []
    assert schema["type"] == "object"


def test_every_tool_uses_dot_notation() -> None:
    assert len(EXPECTED_TOOL_NAMES) == TOOL_COUNT
    for name in EXPECTED_TOOL_NAMES:
        assert "." in name, name
        domain, action = name.split(".", 1)
        assert domain and action, name


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


async def test_prompts_and_resources_are_registered() -> None:
    prompts = await mcp.list_prompts()
    resources = await mcp.list_resources()
    prompt_names = {p.name for p in prompts}
    resource_names = {r.name for r in resources}
    assert "x402.buy_paid_api" in prompt_names
    assert "city.compliance_path" in prompt_names
    assert "x402.instructions" in resource_names
    assert "x402.catalog" in resource_names
    for prompt in prompts:
        assert prompt.description
        for arg in prompt.arguments or []:
            if arg.name:
                assert arg.description, f"{prompt.name}.{arg.name}"
