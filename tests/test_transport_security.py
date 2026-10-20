"""The public host must get through DNS-rebinding protection.

FastMCP allows localhost only by default, so a deployed server answers every
Streamable HTTP request with 421 "Invalid Host header" — it is listed, reachable
by DNS, and completely unusable to a remote MCP client. Found while preparing
registry listings: publishing a broken endpoint is worse than not publishing.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.mcp_server import _transport_security


@pytest.fixture
def public(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://x402-mcp.example.com")


def test_the_public_host_is_allowed(public) -> None:
    s = _transport_security()

    assert "x402-mcp.example.com" in s.allowed_hosts
    assert "https://x402-mcp.example.com" in s.allowed_origins


def test_protection_stays_enabled(public) -> None:
    """Allowlist the host; do not switch the check off."""
    assert _transport_security().enable_dns_rebinding_protection is True


def test_localhost_is_still_allowed(public) -> None:
    s = _transport_security()

    assert "127.0.0.1:*" in s.allowed_hosts
    assert "localhost:*" in s.allowed_hosts


def test_a_local_base_url_still_allows_localhost(monkeypatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8402")

    hosts = _transport_security().allowed_hosts
    assert "127.0.0.1:*" in hosts
    assert "localhost:*" in hosts
    assert "[::1]:*" in hosts


def test_smithery_hosts_and_origins_are_allowed(public) -> None:
    s = _transport_security()
    assert "server.smithery.ai" in s.allowed_hosts
    assert "x402-mcp--kwizzlesurp10.run.tools" in s.allowed_hosts
    assert "https://smithery.ai" in s.allowed_origins
