"""Shared AsyncClient for outbound HTTP (connection reuse, fewer TLS handshakes)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def get_async_http_client() -> httpx.AsyncClient:
    """Lazy singleton with sane defaults for discovery and probe traffic."""
    global _client
    if _client is None:
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            limits=limits,
        )
        logger.debug("shared AsyncClient initialized (httpx keep-alive)")
    return _client


async def aclose_async_http_client() -> None:
    """Close singleton (e.g. app shutdown). Safe to call multiple times."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def bind_async_http_client_for_test(client: httpx.AsyncClient | None) -> None:
    """Test hook: replace singleton."""
    global _client
    _client = client
