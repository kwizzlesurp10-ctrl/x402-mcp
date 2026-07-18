"""GET /probe SSRF guard and rate limiting."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.probe_rate_limit import ProbeRateLimiter
from app.ssrf_guard import SSRFBlockedError, validate_probe_url

client = TestClient(app)


def test_ssrf_blocks_localhost() -> None:
    with pytest.raises(SSRFBlockedError):
        validate_probe_url("http://localhost/paid")


def test_ssrf_blocks_private_ip() -> None:
    with pytest.raises(SSRFBlockedError):
        validate_probe_url("http://10.0.0.1/internal")


def test_ssrf_blocks_file_scheme() -> None:
    with pytest.raises(SSRFBlockedError):
        validate_probe_url("file:///etc/passwd")


def test_ssrf_allows_public_https() -> None:
    assert validate_probe_url("https://example.com/api") == "https://example.com/api"


def test_probe_route_blocks_localhost() -> None:
    response = client.get("/probe", params={"url": "http://127.0.0.1/test"})
    assert response.status_code == 400


def test_probe_rate_limiter_enforces_cap() -> None:
    limiter = ProbeRateLimiter(limit=2, window_seconds=60.0)
    limiter.check("test-ip")
    limiter.check("test-ip")
    from app.probe_rate_limit import ProbeRateLimitExceeded

    with pytest.raises(ProbeRateLimitExceeded):
        limiter.check("test-ip")