"""Agent-facing docs must echo the live paid catalog — no unimplemented SKUs."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from app import agent_surface, diligence_pack
from app.config import settings
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)

STALE_OPEN_PHRASES = (
    "Implement dilated diligence pack",
    "diligence pack is not implemented",
    "diligence pack not implemented",
    "[ ] Seed settlement: first settled mainnet sale",
    "Ship 3–5 more city compliance products",
    "[ ] Implement dilated diligence",
)


def _paid() -> list[dict]:
    return [r for r in agent_surface.paid_resources() if r.get("price") not in (None, "free")]


def _path(url: str) -> str:
    return urlparse(url).path


def test_memory_lists_every_paid_catalog_path_and_price() -> None:
    memory = (ROOT / "MEMORY.md").read_text(encoding="utf-8")
    paid = _paid()
    assert paid, "catalog generator emitted no paid resources"
    for r in paid:
        path = _path(r["url"])
        assert path in memory, f"MEMORY.md missing catalog path {path} ({r['name']})"
        assert r["price"] in memory, f"MEMORY.md missing catalog price {r['price']} for {r['name']}"
        assert r["name"] in memory, f"MEMORY.md missing catalog name {r['name']}"


def test_docs_do_not_treat_live_products_as_open_work() -> None:
    for rel in ("MEMORY.md", "ROADMAP.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for phrase in STALE_OPEN_PHRASES:
            assert phrase not in text, f"{rel} still has stale open-work phrase: {phrase}"


def test_diligence_and_city_unpaid_are_402_not_stubs() -> None:
    """Shipped HTTP doors: unpaid probes must not 404/501; 402 when seller configured."""
    probes = [
        ("GET", "/tasks/us-rental-diligence", None),
        (
            "POST",
            "/tasks/us-rental-diligence",
            {"properties": [{"city_code": "mn", "address": "1700 Penn Ave N"}]},
        ),
        ("GET", "/us/mn/property-check", None),
        ("GET", "/mn/property-check", None),
        ("GET", "/base/tx-decision", None),
    ]
    for method, path, body in probes:
        response = client.request(method, path, json=body)
        assert response.status_code != 404, f"{method} {path} is missing"
        assert response.status_code != 501, f"{method} {path} advertised unimplemented"
        if response.status_code == 503:
            continue
        assert response.status_code == 402, (
            f"{method} {path} unpaid → {response.status_code}, expected 402"
        )
    post = client.post(
        "/tasks/us-rental-diligence",
        json={"properties": [{"city_code": "mn", "address": "1700 Penn Ave N"}]},
    )
    if post.status_code == 402:
        payload = post.json()
        assert payload.get("product_id") == diligence_pack.PRODUCT_ID
        assert settings.diligence_pack_price in (payload.get("price") or "")


def test_catalog_prices_come_from_shipped_settings() -> None:
    by_path = {_path(r["url"]): r["price"] for r in _paid()}
    assert by_path.get("/tasks/us-rental-diligence") == settings.diligence_pack_price
    assert by_path.get("/base/tx-decision") == settings.tx_decision_price
    assert by_path.get("/mn/property-check") == settings.mn_property_check_price
    assert by_path.get("/us/mn/property-check") == settings.city_network_price
