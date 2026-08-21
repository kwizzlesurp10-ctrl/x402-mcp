"""Tests for diligence pack + bazaar metadata phase 1/2."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import diligence_pack
from app.config import settings
from app.main import app
from app.swarm.models import CompositeProduct, purchase_discovery_metadata


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "x402_pay_to_address", "0x" + "ab" * 20)
    monkeypatch.setattr(settings, "diligence_pack_price", "$1.50")
    monkeypatch.setattr(settings, "diligence_pack_min_usdc", 0.75)
    monkeypatch.setattr(settings, "diligence_pack_max_usdc", 2.50)
    monkeypatch.setattr(settings, "public_base_url", "http://test")
    return TestClient(app)


def test_mn_description_under_cdp_ceiling() -> None:
    from app import mn_compliance

    assert len(mn_compliance.RESOURCE_DESCRIPTION) <= 500
    assert "compliance_verdict" in mn_compliance.RESOURCE_DESCRIPTION
    assert "screening" in mn_compliance.SERVICE_TAGS
    assert "property" not in mn_compliance.SERVICE_TAGS or "screening" in mn_compliance.SERVICE_TAGS


def test_pulse_discovery_metadata_has_empty_input() -> None:
    p = CompositeProduct(
        product_id="abc123",
        topic="Base Network Pulse @ block 1",
        cost_basis_usdc=0.0,
        price_usdc=0.05,
        markup=0.0,
        network="eip155:8453",
        sources=[],
        report="# Base Network Pulse - block 1\nline2",
    )
    meta = purchase_discovery_metadata(p, "https://example.com")
    assert meta["discovery_input_example"] == {}
    assert meta["discovery_output_example"]["payment_settled"] is True
    assert meta["discovery_output_example"]["price_usdc"] == 0.05
    assert "purchase" in meta["resource_url"]


def test_price_clamp_rejects_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "diligence_pack_price", "$0.10")
    monkeypatch.setattr(settings, "diligence_pack_min_usdc", 0.75)
    monkeypatch.setattr(settings, "diligence_pack_max_usdc", 2.50)
    with pytest.raises(ValueError, match="outside clamp"):
        diligence_pack.validated_price_usdc()


def test_price_clamp_accepts_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "diligence_pack_price", "$1.50")
    assert diligence_pack.validated_price_usdc() == 1.5
    assert diligence_pack.price_string() == "$1.50"


def test_request_validation_city_and_cap() -> None:
    with pytest.raises(Exception):
        diligence_pack.DiligencePackRequest.model_validate(
            {"properties": [{"city_code": "nope", "address": "1 Main"}]}
        )
    with pytest.raises(Exception):
        diligence_pack.DiligencePackRequest.model_validate(
            {
                "properties": [
                    {"city_code": "mn", "address": f"addr{i}"} for i in range(6)
                ]
            }
        )
    ok = diligence_pack.DiligencePackRequest.model_validate(
        {"properties": [{"city_code": "MN", "address": " 1700 Penn Ave N "}]}
    )
    assert ok.properties[0].city_code == "mn"


def test_risk_summary_mixed() -> None:
    items = [
        {"ok": True, "bucket": "clean"},
        {"ok": True, "bucket": "flagged"},
        {"ok": False, "error": "x"},
    ]
    s = diligence_pack.risk_summary(items)
    assert s["overall"] == "mixed"
    assert s["flagged"] == 1
    assert s["clean"] == 1
    assert s["errors"] == 1


def test_get_returns_402(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        diligence_pack, "build_payment_required_header", lambda: "dGVzdA=="
    )
    r = client.get("/tasks/us-rental-diligence")
    assert r.status_code == 402
    assert r.headers.get("payment-required") == "dGVzdA=="
    body = r.json()
    assert body["error"] == "payment_required"
    assert body["method"] == "POST"
    assert "properties" in body["input_schema"]["properties"]


def test_post_unpaid_402(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        diligence_pack, "build_payment_required_header", lambda: "dGVzdA=="
    )
    r = client.post(
        "/tasks/us-rental-diligence",
        json={"properties": [{"city_code": "mn", "address": "1700 Penn Ave N"}]},
    )
    assert r.status_code == 402
    assert r.json()["product_id"] == diligence_pack.PRODUCT_ID


def test_post_bad_body_422_before_settle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        diligence_pack, "build_payment_required_header", lambda: "dGVzdA=="
    )

    async def must_not_settle(*_a, **_k):  # noqa: ANN001
        raise AssertionError("settle must not run on bad body")

    monkeypatch.setattr(diligence_pack, "verify_and_settle", must_not_settle)
    r = client.post(
        "/tasks/us-rental-diligence",
        headers={"PAYMENT-SIGNATURE": "sig"},
        json={"properties": []},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "validation_error"


@pytest.mark.asyncio
async def test_build_pack_item_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(_addr: str) -> dict:
        raise RuntimeError("arcgis down")

    class FakeMod:
        async def check_property(self, address: str) -> dict:
            return await boom(address)

    monkeypatch.setattr(diligence_pack, "get_city", lambda _c: FakeMod())
    body = diligence_pack.DiligencePackRequest.model_validate(
        {"properties": [{"city_code": "mn", "address": "1 Main St"}]}
    )
    pack = await diligence_pack.build_pack(body, payment_settled=True)
    assert pack["payment_settled"] is True
    assert pack["ok_count"] == 0
    assert pack["properties"][0]["error"] == "upstream_open_data_unavailable"
    assert pack["risk_summary"]["overall"] == "unavailable"


def test_post_paid_happy_path(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        diligence_pack, "build_payment_required_header", lambda: "dGVzdA=="
    )

    async def fake_settle(_sig: str, _pr: str) -> dict:
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"transaction": "0xabc", "payer": "0xbuyer"},
        }

    async def fake_check(city: str, address: str) -> dict:
        return {
            "city_code": city,
            "address": address,
            "ok": True,
            "compliance_verdict": "licensed_clean",
            "bucket": "clean",
            "report": {"compliance_verdict": "licensed_clean"},
        }

    monkeypatch.setattr(diligence_pack, "verify_and_settle", fake_settle)
    monkeypatch.setattr(diligence_pack, "check_one", fake_check)

    rev_calls: list[dict] = []

    def fake_rev(**kwargs):  # noqa: ANN003
        rev_calls.append(kwargs)
        return kwargs

    monkeypatch.setattr(
        "app.swarm.ledger_writer.record_revenue", fake_rev
    )

    r = client.post(
        "/tasks/us-rental-diligence",
        headers={"PAYMENT-SIGNATURE": "sig"},
        json={
            "properties": [{"city_code": "mn", "address": "1700 Penn Ave N"}],
            "idempotency_key": "pack-test-1",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["payment_settled"] is True
    assert body["pack_id"] == "pack-test-1"
    assert body["ok_count"] == 1
    assert body["risk_summary"]["overall"] == "clear"
    assert r.headers.get("payment-response")
    assert rev_calls and rev_calls[0]["product_id"] == diligence_pack.PRODUCT_ID


def test_agent_surface_lists_diligence() -> None:
    from app import agent_surface

    urls = [r["url"] for r in agent_surface.paid_resources()]
    assert any(u.endswith("/tasks/us-rental-diligence") for u in urls)
    card = agent_surface.agent_card()
    skill_ids = {s["id"] for s in card["skills"]}
    assert "us-rental-diligence-pack" in skill_ids
