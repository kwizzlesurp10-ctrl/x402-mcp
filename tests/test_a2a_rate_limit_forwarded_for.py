"""A2A creation rate limit: X-Forwarded-For only when reverse-proxy peer is trusted."""

from __future__ import annotations

import pytest
from starlette.datastructures import Headers

from app.a2a_rpc import _check_a2a_creation_rate, _creation_buckets, _rate_limit_client_ip, clear_task_store


@pytest.fixture(autouse=True)
def _fresh() -> None:
    clear_task_store()
    _creation_buckets.clear()
    yield
    _creation_buckets.clear()
    clear_task_store()


def test_rate_limit_ip_ignores_xff_when_peer_untrusted() -> None:
    hdr = Headers({"x-forwarded-for": "198.51.100.7"})
    assert _rate_limit_client_ip(hdr, request_scope={"x402.peer_trusted": False}) == "unknown"
    assert _rate_limit_client_ip(hdr, request_scope=None) == "unknown"


def test_rate_limit_ip_uses_xff_when_peer_trusted() -> None:
    hdr = Headers({"x-forwarded-for": "198.51.100.7, 10.0.0.1"})
    ip = _rate_limit_client_ip(hdr, request_scope={"x402.peer_trusted": True})
    assert ip == "198.51.100.7"


def test_cf_connecting_ip_ignored_when_peer_untrusted() -> None:
    """Direct clients can forge CF-Connecting-IP; only trust reverse-proxy peers."""
    hdr = Headers(
        {
            "cf-connecting-ip": "198.51.100.1",
            "x-forwarded-for": "198.51.100.99",
        }
    )
    assert _rate_limit_client_ip(hdr, request_scope={"x402.peer_trusted": False}) == "unknown"


def test_cf_connecting_ip_takes_precedence_over_xff_when_trusted() -> None:
    hdr = Headers(
        {
            "cf-connecting-ip": "198.51.100.1",
            "x-forwarded-for": "198.51.100.99",
        }
    )
    assert _rate_limit_client_ip(hdr, request_scope={"x402.peer_trusted": True}) == "198.51.100.1"


def test_xff_spoof_does_not_bypass_limit_for_direct_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Untrusted hop: all clients share the ``unknown`` bucket regardless of XFF."""
    monkeypatch.setattr("app.a2a_rpc._A2A_CREATE_LIMIT", 2)
    _creation_buckets.clear()
    untrusted = {"x402.peer_trusted": False}
    for fake_ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        hdr = Headers({"x-forwarded-for": fake_ip})
        res = _check_a2a_creation_rate(hdr, request_scope=untrusted)
        if fake_ip == "10.0.0.3":
            assert res == "a2a task creation rate limited"
        else:
            assert res is None


def test_distinct_xff_behind_trusted_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.a2a_rpc._A2A_CREATE_LIMIT", 2)
    _creation_buckets.clear()
    trusted = {"x402.peer_trusted": True}
    h1 = Headers({"x-forwarded-for": "198.51.100.10"})
    h2 = Headers({"x-forwarded-for": "198.51.100.11"})
    assert _check_a2a_creation_rate(h1, request_scope=trusted) is None
    assert _check_a2a_creation_rate(h1, request_scope=trusted) is None
    assert _check_a2a_creation_rate(h1, request_scope=trusted) == "a2a task creation rate limited"
    assert _check_a2a_creation_rate(h2, request_scope=trusted) is None
