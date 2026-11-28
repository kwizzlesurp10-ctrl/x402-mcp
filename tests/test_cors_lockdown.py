"""CORS: exact-origin env allowlist, explicit headers/methods, no '*'."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import main
from app.config import settings

client = TestClient(main.app)


def _preflight(origin: str, headers: str = "content-type"):
    return client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": headers,
        },
    )


def test_main_app_cors_has_no_wildcards() -> None:
    for mw in main.app.user_middleware:
        if mw.cls.__name__ == "CORSMiddleware":
            kw = mw.kwargs
            assert "*" not in kw["allow_origins"]
            assert "*" not in kw["allow_headers"]
            assert "*" not in kw["allow_methods"]
            break
    else:  # pragma: no cover
        raise AssertionError("CORSMiddleware not installed")


def test_preflight_allowed_origin_and_header() -> None:
    r = _preflight("https://kwizzlesurp.com", "authorization,content-type,payment-signature")
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://kwizzlesurp.com"
    assert "*" not in r.headers.get("access-control-allow-headers", "")


def test_preflight_unknown_origin_rejected() -> None:
    r = _preflight("https://evil.example")
    assert r.status_code == 400
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_preflight_unlisted_header_rejected() -> None:
    r = _preflight("https://kwizzlesurp.com", "x-totally-custom")
    assert r.status_code == 400


def test_env_allowlist_replaces_defaults_and_drops_wildcards(monkeypatch) -> None:
    monkeypatch.setattr(settings, "cors_allowed_origins", "https://a.example, *, https://b.example/")
    monkeypatch.setattr(settings, "cors_extra_origins", "https://c.example")
    assert main._cors_origins() == ["https://a.example", "https://b.example", "https://c.example"]


def test_extra_origins_env_is_read(monkeypatch) -> None:
    monkeypatch.setattr(settings, "cors_allowed_origins", "")
    monkeypatch.setattr(settings, "cors_extra_origins", "https://partner.example")
    origins = main._cors_origins()
    assert "https://partner.example" in origins
    assert "https://kwizzlesurp.com" in origins


def test_mcp_cors_defaults_to_allowlist_and_star_is_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.setattr(settings, "mcp_cors_origins", "")
    assert "*" not in main._mcp_cors_origins()
    monkeypatch.setattr(settings, "mcp_cors_origins", "*")
    assert main._mcp_cors_origins() == ["*"]
