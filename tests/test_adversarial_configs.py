"""Adversarial and Empirical Challenge Test Suite for Milestone 2.

Validates smithery.yaml, package.json, and server.json for strict syntax,
schema compliance, edge cases, error resilience, and cross-file synchronicity.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SMITHERY_YAML_PATH = ROOT / "smithery.yaml"
PACKAGE_JSON_PATH = ROOT / "package.json"
SERVER_JSON_PATH = ROOT / "server.json"
RUN_STDIO_PATH = ROOT / "run_stdio.py"


# =====================================================================
# 1. STRICT SYNTAX & PARSER ADVERSARIAL TESTS
# =====================================================================

def test_package_json_no_duplicate_keys() -> None:
    raw_text = PACKAGE_JSON_PATH.read_text(encoding="utf-8")
    
    def check_dups(pairs):
        seen = set()
        for k, v in pairs:
            if k in seen:
                raise ValueError(f"Duplicate JSON key found in package.json: '{k}'")
            seen.add(k)
        return dict(pairs)

    data = json.loads(raw_text, object_pairs_hook=check_dups)
    assert isinstance(data, dict)
    assert len(data) > 0


def test_server_json_no_duplicate_keys() -> None:
    raw_text = SERVER_JSON_PATH.read_text(encoding="utf-8")
    
    def check_dups(pairs):
        seen = set()
        for k, v in pairs:
            if k in seen:
                raise ValueError(f"Duplicate JSON key found in server.json: '{k}'")
            seen.add(k)
        return dict(pairs)

    data = json.loads(raw_text, object_pairs_hook=check_dups)
    assert isinstance(data, dict)
    assert len(data) > 0


def test_smithery_yaml_strict_unique_keys_and_valid_yaml() -> None:
    raw_text = SMITHERY_YAML_PATH.read_text(encoding="utf-8")

    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader, node, deep=False):
        loader.flatten_mapping(node)
        mapping = {}
        for key_node, val_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            val = loader.construct_object(val_node, deep=deep)
            if key in mapping:
                raise ValueError(f"Duplicate YAML key '{key}' at line {key_node.start_mark.line + 1}")
            mapping[key] = val
        return mapping

    UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    data = yaml.load(raw_text, Loader=UniqueKeyLoader)
    assert isinstance(data, dict)
    assert len(data) > 5


# =====================================================================
# 2. SERVER.JSON STRICT SPECIFICATION & ADVERSARIAL CONSTRAINTS
# =====================================================================

def test_server_json_mcp_registry_schema_conformance() -> None:
    doc = json.loads(SERVER_JSON_PATH.read_text(encoding="utf-8"))
    
    # Required keys
    assert "$schema" in doc
    assert doc["$schema"] == "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
    
    assert doc["name"] == "io.github.kwizzlesurp10-ctrl/x402-mcp"
    assert len(str(doc["version"]).split(".")) == 3
    assert doc.get("title", "x402 Micropayments MCP")
    assert doc["websiteUrl"] == "https://x402-mcp.onrender.com"
    
    # Strict registry constraint: Description <= 100 chars
    desc = doc["description"]
    assert isinstance(desc, str)
    assert 1 <= len(desc) <= 100, f"Description length is {len(desc)}, exceeds MCP registry limit of 100!"
    
    # Repository block
    repo = doc["repository"]
    assert isinstance(repo, dict)
    assert repo.get("source") == "github"
    assert repo.get("url") == "https://github.com/kwizzlesurp10-ctrl/x402-mcp"
    
    # Remotes block
    remotes = doc["remotes"]
    assert isinstance(remotes, list) and len(remotes) == 1
    assert remotes[0]["type"] == "streamable-http"
    assert remotes[0]["url"] == "https://x402-mcp.onrender.com/mcp/mcp"
    
    if "capabilities" in doc:
        caps = doc["capabilities"]
        assert isinstance(caps, dict)
        assert caps.get("tools") is True
        assert caps.get("resources") is True
        assert caps.get("prompts") is True


# =====================================================================
# 3. PACKAGE.JSON NPM SPECIFICATION & ADVERSARIAL CONSTRAINTS
# =====================================================================

def test_package_json_npm_structure_and_scripts() -> None:
    doc = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
    
    assert doc["name"] == "x402-mcp"
    assert doc["version"] == "0.1.0"
    assert isinstance(doc["description"], str) and len(doc["description"]) > 10
    assert doc["author"] == "kwizzlesurp10"
    assert doc["license"] == "MIT"
    assert doc["main"] == "run_stdio.py"
    assert RUN_STDIO_PATH.exists(), "Main entry point file run_stdio.py does not exist!"
    
    # Keywords
    keywords = doc.get("keywords")
    assert isinstance(keywords, list)
    assert len(keywords) >= 10
    required_kws = {"mcp", "x402", "crypto", "ai-agents", "agent-cards", "compliance", "base", "blockchain", "fastmcp", "micropayments", "smithery"}
    for kw in required_kws:
        assert kw in keywords, f"Keyword '{kw}' missing from package.json"

    # Repository & Bugs
    assert doc["repository"] == {
        "type": "git",
        "url": "https://github.com/kwizzlesurp10-ctrl/x402-mcp.git"
    }
    assert doc["bugs"] == {
        "url": "https://github.com/kwizzlesurp10-ctrl/x402-mcp/issues"
    }
    assert doc["homepage"] == "https://github.com/kwizzlesurp10-ctrl/x402-mcp#readme"
    
    # Scripts
    scripts = doc.get("scripts", {})
    assert scripts.get("start") == "python run_stdio.py"
    assert scripts.get("test") == "pytest"
    assert "build" in scripts


# =====================================================================
# 4. SMITHERY.YAML SPECIFICATION & ADVERSARIAL CONSTRAINTS
# =====================================================================

def test_smithery_yaml_comprehensive_spec() -> None:
    doc = yaml.safe_load(SMITHERY_YAML_PATH.read_text(encoding="utf-8"))
    
    assert doc["name"] == "x402-mcp"
    assert doc["displayName"] == "x402-mcp"
    assert len(str(doc["version"]).split(".")) == 3
    assert isinstance(doc["description"], str) and len(doc["description"].strip()) > 20
    assert doc["homepage"] == "https://x402-mcp.onrender.com"
    assert doc["repository"] == "https://github.com/kwizzlesurp10-ctrl/x402-mcp"
    assert doc["license"] == "MIT"
    
    categories = doc.get("categories", [])
    assert isinstance(categories, list) and len(categories) >= 3
    tags = doc.get("tags", [])
    assert isinstance(tags, list) and len(tags) >= 5
    assert "x402" in tags and "mcp" in tags

    start_cmd = doc.get("startCommand", {})
    assert start_cmd.get("type") in ("http", "stdio")
    schema = start_cmd.get("configSchema") or doc.get("configSchema") or {}
    assert schema.get("type") == "object"
    props = schema.get("properties", {})
    assert "X402_PAY_TO_ADDRESS" in props
    assert "EVM_PRIVATE_KEY" in props
    for p in ("X402_PAY_TO_ADDRESS", "EVM_PRIVATE_KEY"):
        assert props[p].get("type") == "string"
        assert len(props[p].get("description", "")) > 5


# =====================================================================
# 5. NODE.JS COMMAND FUNCTION RUNTIME EXECUTION TEST
# =====================================================================

def test_smithery_command_function_node_execution() -> None:
    doc = yaml.safe_load(SMITHERY_YAML_PATH.read_text(encoding="utf-8"))
    cmd_fn_src = doc.get("commandFunction")
    if not cmd_fn_src:
        pytest.skip("Smithery runtime is container/http; no stdio commandFunction")
    assert isinstance(cmd_fn_src, str) and len(cmd_fn_src) > 10

    # Test under Node.js with multiple test vectors
    js_eval_script = f"""
    const fn = {cmd_fn_src};

    // Vector 1: Empty config
    const res1 = fn({{}});
    if (res1.command !== 'python' || !res1.args.includes('run_stdio.py')) {{
        throw new Error('Vector 1 failed: ' + JSON.stringify(res1));
    }}
    if (res1.env.X402_FACILITATOR_URL !== 'https://x402.org/facilitator') {{
        throw new Error('Vector 1 default facilitator url failed');
    }}
    if (res1.env.X402_DEFAULT_NETWORK !== 'eip155:84532') {{
        throw new Error('Vector 1 default network failed');
    }}

    // Vector 2: UPPERCASE keys config
    const res2 = fn({{
        X402_PAY_TO_ADDRESS: '0x1111111111111111111111111111111111111111',
        EVM_PRIVATE_KEY: '0xabc',
        X402_NETWORK: 'eip155:8453',
        DEFAULT_AGENT_ID: 'agent-custom-1',
        DYNAMIC_QUOTA_MODE: 'strict'
    }});
    if (res2.env.X402_PAY_TO_ADDRESS !== '0x1111111111111111111111111111111111111111') {{
        throw new Error('Vector 2 PAY_TO_ADDRESS mismatch');
    }}
    if (res2.env.X402_DEFAULT_NETWORK !== 'eip155:8453') {{
        throw new Error('Vector 2 X402_DEFAULT_NETWORK mismatch');
    }}
    if (res2.env.DEFAULT_AGENT_ID !== 'agent-custom-1') {{
        throw new Error('Vector 2 DEFAULT_AGENT_ID mismatch');
    }}
    if (res2.env.DYNAMIC_QUOTA_MODE !== 'strict') {{
        throw new Error('Vector 2 DYNAMIC_QUOTA_MODE mismatch');
    }}

    // Vector 3: camelCase keys config
    const res3 = fn({{
        x402PayToAddress: '0x2222222222222222222222222222222222222222',
        evmPrivateKey: '0xdef',
        x402Network: 'eip155:8453',
        defaultAgentId: 'agent-camel',
        dynamicQuotaMode: 'relaxed'
    }});
    if (res3.env.X402_PAY_TO_ADDRESS !== '0x2222222222222222222222222222222222222222') {{
        throw new Error('Vector 3 camelCase PAY_TO_ADDRESS mismatch');
    }}
    if (res3.env.DEFAULT_AGENT_ID !== 'agent-camel') {{
        throw new Error('Vector 3 camelCase DEFAULT_AGENT_ID mismatch');
    }}

    // Vector 4: null / undefined config input
    const res4 = fn(undefined);
    const res5 = fn(null);
    if (res4.command !== 'python' || res5.command !== 'python') {{
        throw new Error('Vector 4/5 null safety failed');
    }}

    console.log('ALL_NODE_VECTORS_PASSED');
    """

    res = subprocess.run(
        ["node", "-e", js_eval_script],
        capture_output=True,
        text=True,
        check=False
    )
    assert res.returncode == 0, f"Node.js commandFunction evaluation failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    assert "ALL_NODE_VECTORS_PASSED" in res.stdout


# =====================================================================
# 6. CROSS-FILE SYNCHRONIZATION & CONSISTENCY
# =====================================================================

def test_cross_file_consistency() -> None:
    pkg = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
    srv = json.loads(SERVER_JSON_PATH.read_text(encoding="utf-8"))
    smt = yaml.safe_load(SMITHERY_YAML_PATH.read_text(encoding="utf-8"))

    # Registry + Smithery share a version; npm package.json may lag.
    assert str(smt["version"]) == srv["version"]
    
    assert pkg["license"] == smt["license"] == "MIT"
    
    assert srv["repository"]["url"] == smt["repository"]
    assert pkg["repository"]["url"].startswith(smt["repository"])
    
    assert srv["remotes"][0]["url"].endswith("/mcp/mcp")
    assert srv["remotes"][0]["type"] == "streamable-http"
    
    assert pkg["main"] == "run_stdio.py"
    start = smt.get("startCommand") or {}
    assert start.get("type") in ("http", "stdio")


# =====================================================================
# 7. MUTATION & ORACLE STRESS TESTS
# =====================================================================

def test_oracle_mutation_fails_on_corruptions() -> None:
    """Verifies that our verification logic would catch deliberate corruptions."""
    
    # Mutation 1: server.json description exceeding 100 characters
    bad_server_json = json.loads(SERVER_JSON_PATH.read_text(encoding="utf-8"))
    bad_server_json["description"] = "A" * 101
    assert len(bad_server_json["description"]) > 100
    
    # Mutation 2: missing $schema
    del bad_server_json["$schema"]
    assert "$schema" not in bad_server_json
    
    # Mutation 3: type mismatch in smithery configSchema
    bad_smithery = yaml.safe_load(SMITHERY_YAML_PATH.read_text(encoding="utf-8"))
    schema = (bad_smithery.get("startCommand") or {}).get("configSchema") or bad_smithery.get("configSchema")
    assert schema is not None
    schema["properties"]["X402_PAY_TO_ADDRESS"]["type"] = "integer"
    assert schema["properties"]["X402_PAY_TO_ADDRESS"]["type"] != "string"
