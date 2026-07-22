"""server.json stays valid for the MCP registry.

Publishing rejects an invalid manifest, and the constraints are easy to trip —
description caps at 100 characters, which the first draft of this file exceeded.
The remote URL is pinned too: it must be the Streamable HTTP path the app
actually mounts (/mcp/mcp), not the /mcp/sse the manifest advertises.
"""

from __future__ import annotations

import json
import pathlib

import pytest

DOC = json.loads(
    (pathlib.Path(__file__).resolve().parents[1] / "server.json").read_text(
        encoding="utf-8"
    )
)


def test_required_fields_present() -> None:
    for field in ("$schema", "name", "version", "remotes"):
        assert field in DOC, field


def test_description_fits_the_registry_limit() -> None:
    assert 1 <= len(DOC["description"]) <= 100


def test_namespace_matches_the_github_owner() -> None:
    """io.github.<owner>/<name> is only publishable by that GitHub account."""
    assert DOC["name"].startswith("io.github.kwizzlesurp10-ctrl/")


def test_the_remote_points_at_the_mounted_transport() -> None:
    remote = DOC["remotes"][0]

    assert remote["type"] == "streamable-http"
    # FastMCP mounts at /mcp and serves its own /mcp beneath it.
    assert remote["url"].endswith("/mcp/mcp")


@pytest.mark.skipif(
    not pathlib.Path(".git").exists(), reason="version check needs the repo"
)
def test_version_is_semver() -> None:
    parts = DOC["version"].split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)
