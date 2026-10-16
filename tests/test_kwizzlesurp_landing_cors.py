"""Landing page on kwizzlesurp.com must be allowed to read /health."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_kwizzlesurp_origin_can_read_health() -> None:
    response = client.get("/health", headers={"Origin": "https://kwizzlesurp.com"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://kwizzlesurp.com"
    assert response.json()["status"] == "ok"


def test_www_kwizzlesurp_origin_can_read_health() -> None:
    response = client.get("/health", headers={"Origin": "https://www.kwizzlesurp.com"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://www.kwizzlesurp.com"
