"""Diligence pack is a live paid product — docs must not call it unimplemented."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import agent_surface, diligence_pack
from app.config import settings
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)

STALE_UNIMPLEMENTED = (
    "Implement dilated diligence pack",
    "diligence pack is not implemented",
    "diligence pack not implemented",
)


def test_shipped_pack_has_catalog_price_and_route() -> None:
    price = diligence_pack.price_string()
    assert price == settings.diligence_pack_price
    assert diligence_pack.validated_price_usdc() > 0
    assert diligence_pack.resource_url().endswith("/tasks/us-rental-diligence")


def test_http_route_is_a_paid_door_not_a_stub() -> None:
    """Unpaid GET/POST must 402 from the shipped FastAPI route, not 404/501."""
    get_r = client.get("/tasks/us-rental-diligence")
    post_r = client.post(
        "/tasks/us-rental-diligence",
        json={"properties": [{"city_code": "mn", "address": "1700 Penn Ave N"}]},
    )
    assert get_r.status_code != 404
    assert post_r.status_code != 404
    assert get_r.status_code != 501
    assert post_r.status_code != 501
    if get_r.status_code == 503:
        return  # seller unset in this process; route still exists
    assert get_r.status_code == 402
    assert post_r.status_code == 402
    assert post_r.json().get("product_id") == diligence_pack.PRODUCT_ID
    assert settings.diligence_pack_price in (post_r.json().get("price") or "")


def test_agent_catalog_lists_pack_at_config_price() -> None:
    paid = agent_surface.paid_resources()
    match = [r for r in paid if r["url"].endswith("/tasks/us-rental-diligence")]
    assert match, "diligence pack missing from live catalog generator"
    assert match[0]["price"] == settings.diligence_pack_price
    skill_ids = {s["id"] for s in agent_surface.agent_card()["skills"]}
    assert "us-rental-diligence-pack" in skill_ids


def test_memory_and_roadmap_do_not_list_pack_as_unimplemented() -> None:
    for rel in ("MEMORY.md", "ROADMAP.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for phrase in STALE_UNIMPLEMENTED:
            assert phrase not in text, f"{rel} still lists diligence pack as unimplemented"
        assert "[ ] Implement dilated diligence" not in text
    memory = (ROOT / "MEMORY.md").read_text(encoding="utf-8")
    assert "/tasks/us-rental-diligence" in memory
    assert "[x]" in memory
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    assert "/tasks/us-rental-diligence" in roadmap
