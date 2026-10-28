"""Validation test suite for server.json, package.json, and smithery.yaml.

Ensures that all metadata manifests stay valid, discoverable, and synchronized
across MCP Registry, NPM, and Smithery.ai specifications.
"""

from __future__ import annotations

import json
import pathlib
import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVER_JSON_PATH = ROOT / "server.json"
PACKAGE_JSON_PATH = ROOT / "package.json"
SMITHERY_YAML_PATH = ROOT / "smithery.yaml"

SERVER_DOC = json.loads(SERVER_JSON_PATH.read_text(encoding="utf-8"))
PACKAGE_DOC = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
SMITHERY_DOC = yaml.safe_load(SMITHERY_YAML_PATH.read_text(encoding="utf-8")) if SMITHERY_YAML_PATH.exists() else {}


# --- server.json tests ---

def test_server_json_required_fields_present() -> None:
    for field in ("$schema", "name", "version", "description", "repository", "remotes", "homepage"):
        assert field in SERVER_DOC, f"Missing required field: {field}"


def test_server_json_description_fits_the_registry_limit() -> None:
    assert 1 <= len(SERVER_DOC["description"]) <= 200


def test_server_json_namespace_matches_the_github_owner() -> None:
    """io.github.<owner>/<name> is only publishable by that GitHub account."""
    assert SERVER_DOC["name"].startswith("io.github.kwizzlesurp10-ctrl/")


def test_server_json_the_remote_points_at_the_mounted_transport() -> None:
    remote = SERVER_DOC["remotes"][0]
    assert remote["type"] == "streamable-http"
    assert "/mcp" in remote["url"]


def test_server_json_x402_payment_block() -> None:
    x402 = SERVER_DOC.get("x402", {})
    assert x402.get("network") == "eip155:8453"
    assert x402.get("chainId") == 8453
    assert x402.get("token") == "USDC"
    assert x402.get("tokenContract") == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    assert x402.get("payTo") == "0xAB745e5F576667037696e78ba7dA28E193E4423D"
    assert x402.get("priceUnits") == "10000"


@pytest.mark.skipif(
    not pathlib.Path(".git").exists(), reason="version check needs the repo"
)
def test_server_json_version_is_semver() -> None:
    parts = SERVER_DOC["version"].split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)


def test_server_json_capabilities() -> None:
    """MCP registry server.json (2025-12-11) has no capabilities block.
    Tools/resources/prompts live on the live server card, not this file."""
    remotes = SERVER_DOC.get("remotes") or []
    assert remotes and remotes[0].get("type") == "streamable-http"
    if "capabilities" in SERVER_DOC:
        caps = SERVER_DOC["capabilities"]
        assert caps.get("tools") is True
        assert caps.get("resources") is True
        assert caps.get("prompts") is True


# --- package.json tests ---

def test_package_json_metadata_fields() -> None:
    assert PACKAGE_DOC["name"] == "x402-mcp"
    assert PACKAGE_DOC["version"] == "0.1.0"
    assert PACKAGE_DOC["author"] == "kwizzlesurp10"
    assert PACKAGE_DOC["license"] == "MIT"
    desc = PACKAGE_DOC["description"].lower()
    assert "x402" in desc
    assert "usdc" in desc
    assert "agent" in desc


def test_package_json_keywords() -> None:
    keywords = set(PACKAGE_DOC.get("keywords", []))
    required = {"mcp", "x402", "crypto", "ai-agents", "agent-cards", "compliance", "base", "blockchain", "fastmcp"}
    assert required.issubset(keywords), f"Missing required keywords: {required - keywords}"


def test_package_json_repository_and_links() -> None:
    repo = PACKAGE_DOC.get("repository", {})
    assert repo.get("type") == "git"
    assert "kwizzlesurp10-ctrl/x402-mcp" in repo.get("url", "")
    assert "kwizzlesurp10-ctrl/x402-mcp" in PACKAGE_DOC.get("homepage", "")
    assert "kwizzlesurp10-ctrl/x402-mcp/issues" in PACKAGE_DOC.get("bugs", {}).get("url", "")


def test_package_json_scripts() -> None:
    scripts = PACKAGE_DOC.get("scripts", {})
    assert "start" in scripts
    assert "test" in scripts
    assert "build" in scripts


# --- smithery.yaml retirement tests ---

def test_smithery_artifacts_retired() -> None:
    assert not SMITHERY_YAML_PATH.exists()


# --- Cross-file sync tests ---

def test_cross_file_metadata_synchronization() -> None:
    if SMITHERY_YAML_PATH.exists():
        assert str(SMITHERY_DOC["version"]) == SERVER_DOC["version"]
        assert PACKAGE_DOC["license"] == SMITHERY_DOC["license"] == "MIT"
    else:
        assert PACKAGE_DOC["license"] == "MIT"
    assert SERVER_DOC["repository"]["url"] == SMITHERY_DOC["repository"]
    assert PACKAGE_DOC["repository"]["url"].startswith(SERVER_DOC["repository"]["url"])
    assert SERVER_DOC["remotes"][0]["url"].endswith("/mcp/mcp")
