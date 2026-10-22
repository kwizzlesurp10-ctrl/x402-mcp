"""Forwarded headers are trusted only from configured proxies (never '*')."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import main
from app.config import settings


def _probe_app(proxies: list[str]) -> TestClient:
    main.set_trusted_proxies(proxies)
    probe = FastAPI()
    probe.add_middleware(main.TrustedProxyHeadersMiddleware, trusted_hosts=proxies)

    @probe.get("/whoami")
    async def whoami(request: Request) -> dict:
        return {
            "ip": request.client.host if request.client else None,
            "scheme": request.url.scheme,
            "peer_trusted": request.scope.get("x402.peer_trusted"),
        }

    return TestClient(probe)


def teardown_function() -> None:
    main.set_trusted_proxies([])


def test_default_trusts_nobody_spoofed_xff_ignored() -> None:
    c = _probe_app([])
    r = c.get("/whoami", headers={"X-Forwarded-For": "1.2.3.4", "X-Forwarded-Proto": "https"}).json()
    assert r["ip"] == "testclient"
    assert r["scheme"] == "http"
    assert r["peer_trusted"] is False


def test_trusted_proxy_uses_rightmost_untrusted_hop() -> None:
    c = _probe_app(["testclient"])
    r = c.get(
        "/whoami",
        headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.9", "X-Forwarded-Proto": "https"},
    ).json()
    # The client-supplied left entry (6.6.6.6) must not win.
    assert r["ip"] == "203.0.113.9"
    assert r["scheme"] == "https"
    assert r["peer_trusted"] is True


def test_star_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxies", "*, 10.0.0.1")
    monkeypatch.delenv("RENDER", raising=False)
    assert main.resolve_trusted_proxies() == ["10.0.0.1"]


def test_unset_trusts_none_off_render(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxies", "")
    monkeypatch.delenv("RENDER", raising=False)
    assert main.resolve_trusted_proxies() == []


def test_render_default_is_private_ranges(monkeypatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxies", "")
    monkeypatch.setenv("RENDER", "true")
    assert main.resolve_trusted_proxies() == main.RENDER_DEFAULT_TRUSTED_PROXIES.split(",")
