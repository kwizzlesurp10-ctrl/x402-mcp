"""Dashboard route — served HTML wires to real API endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_redirects_to_dashboard() -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/dashboard"


def test_dashboard_serves_html() -> None:
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_dashboard_polls_real_endpoints() -> None:
    """The UI must consume live API routes, not hardcoded data."""
    html = client.get("/dashboard").text
    for endpoint in (
        "/health",
        "/quota/",
        "/.well-known/mcp",
        "/upgrade",
        "/swarm/products",
        "/swarm/revenue",
        "/ledger/revenue",
    ):
        assert endpoint in html


def test_dashboard_endpoints_it_polls_are_live() -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/quota/dashboard-agent").status_code == 200
    assert client.get("/.well-known/mcp").status_code == 200
    assert client.get("/upgrade").status_code == 200
    assert client.get("/swarm/products").status_code == 200
    assert client.get("/swarm/revenue").status_code == 200
    assert client.get("/ledger/revenue").status_code == 200


def test_storefront_panel_is_rendered() -> None:
    """The commerce panel needs the element ids its poller writes into."""
    html = client.get("/dashboard").text
    for element_id in (
        "s-revenue",
        "s-spend",
        "s-listed",
        "store-body",
        "sales-body",
    ):
        assert f'id="{element_id}"' in html


def test_storefront_poll_is_throttled_and_visibility_gated() -> None:
    """Those endpoints hit Redis, which is metered — polling must stay cheap.

    Guards two easy regressions: dropping pollStore to the 5s cadence the
    health poller uses, and losing the hidden-tab check that stops a
    backgrounded tab from spending the command budget all day.
    """
    html = client.get("/dashboard").text
    assert "setInterval(pollStore, 30000)" in html
    assert "if (document.hidden) return;" in html
