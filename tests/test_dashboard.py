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
    for endpoint in ("/health", "/quota/", "/.well-known/mcp", "/upgrade"):
        assert endpoint in html


def test_dashboard_endpoints_it_polls_are_live() -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/quota/dashboard-agent").status_code == 200
    assert client.get("/.well-known/mcp").status_code == 200
    assert client.get("/upgrade").status_code == 200
