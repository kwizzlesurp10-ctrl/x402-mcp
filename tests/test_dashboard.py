"""Dashboard route — Mission Control SPA (Vercel layout) on /dashboard."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

BASE_APP_ID_META = 'name="base:app_id" content="6a7018e2a8c4f2b6db3b3e71"'
MC_DIST = Path(__file__).resolve().parents[1] / "app" / "static" / "mission_control"


def test_root_serves_ownership_meta_and_points_at_dashboard() -> None:
    """`/` must expose Base ownership meta for scrapers (not a bare 307)."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert BASE_APP_ID_META in response.text
    assert 'content="0; url=/dashboard"' in response.text or 'href="/dashboard"' in response.text


def test_mission_control_bundle_is_present() -> None:
    assert (MC_DIST / "index.html").is_file(), "SPA index missing — build dashboard/"
    assets = list((MC_DIST / "assets").glob("index-*.js"))
    assert assets, "SPA JS bundle missing under app/static/mission_control/assets"


def test_dashboard_serves_mission_control_spa() -> None:
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert BASE_APP_ID_META in html
    assert "x402 // mission control" in html
    assert 'id="root"' in html
    assert "/assets/" in html
    # Must not still be the legacy IBM Plex terminal shell as the primary UI.
    assert "x402 terminal" not in html


def test_dashboard_trailing_slash() -> None:
    assert client.get("/dashboard/").status_code == 200


def test_dashboard_assets_are_served() -> None:
    html = client.get("/dashboard").text
    # Pull hashed asset paths from the index the server actually returned.
    import re

    js = re.search(r'src="(/assets/[^"]+\.js)"', html)
    css = re.search(r'href="(/assets/[^"]+\.css)"', html)
    assert js and css, html[:500]
    js_resp = client.get(js.group(1))
    css_resp = client.get(css.group(1))
    assert js_resp.status_code == 200, js.group(1)
    assert css_resp.status_code == 200, css.group(1)
    assert "javascript" in js_resp.headers.get("content-type", "") or js_resp.content[:20]
    # Same-origin SPA: no hard-coded remote API host in the bundle.
    assert b"x402-mission-control.onrender.com" not in js_resp.content


def test_dashboard_api_surface_is_live() -> None:
    """SPA polls these same-origin routes (Vercel layout / client.ts)."""
    for path in (
        "/health",
        "/stats",
        "/doctor",
        "/wallet",
        "/ledger/spend",
        "/ledger/revenue",
        "/swarm/products",
        "/swarm/revenue",
        "/upgrade",
        "/.well-known/mcp",
    ):
        assert client.get(path).status_code == 200, path


def test_legacy_terminal_still_available() -> None:
    """Rollback path keeps the old single-file terminal."""
    response = client.get("/dashboard/legacy")
    assert response.status_code == 200
    assert "x402 terminal" in response.text or "quota" in response.text.lower()
