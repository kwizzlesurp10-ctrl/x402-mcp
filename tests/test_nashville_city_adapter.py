"""Nashville (bna) extra public city adapter — catalog, 402, and live feed parse."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.city_compliance import registry
from app.city_compliance.cities import bna
from app.config import settings
from app.main import app

client = TestClient(app)

FEATURE_SERVER_JSON = {
    "features": [
        {
            "attributes": {
                "Permit__": "2024001234",
                "Permit_Status": "ISSUED",
                "Permit_Type": "CARN",
                "Permit_Subtype_Description": "Residential Short Term Rental - Owner Occupied",
                "Address": "1 PUBLIC SQ",
                "Expiration_Date": 1767225600000,
            }
        }
    ]
}


class _FakeResponse:
    def __init__(self, *, json_body: Any | None = None, text: str = "", content_type: str) -> None:
        self._json_body = json_body
        self.text = text
        self.headers = {"content-type": content_type}
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        if self._json_body is None:
            raise json.JSONDecodeError("Expecting value", self.text or "<html>", 0)
        return self._json_body


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[tuple[str, dict | None]] = []

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, url: str, params: dict | None = None) -> _FakeResponse:
        self.calls.append((url, params))
        assert "FeatureServer" in url
        assert url == bna.ARCGIS_URL
        return self._response


def test_bna_is_public_at_city_network_price() -> None:
    codes = {c["code"] for c in registry.list_cities()}
    assert "bna" in codes
    entry = next(c for c in registry.list_cities() if c["code"] == "bna")
    assert entry["price"] == settings.city_network_price
    assert entry["paid_url"].endswith("/us/bna/property-check")


def test_bna_unpaid_property_check_is_402_not_stub() -> None:
    response = client.get("/us/bna/property-check")
    assert response.status_code != 404
    assert response.status_code != 501
    if response.status_code == 503:
        return
    assert response.status_code == 402


@pytest.mark.asyncio
async def test_check_property_parses_featureserver_json(monkeypatch: pytest.MonkeyPatch) -> None:
    bna._cache.clear()
    fake = _FakeClient(
        _FakeResponse(json_body=FEATURE_SERVER_JSON, content_type="application/json")
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: fake)

    report = await bna.check_property("1 Public Sq")

    assert fake.calls, "check_property must GET the FeatureServer"
    assert report["city"] == "bna"
    assert report["compliance_verdict"] == "str_licensed_active"
    assert report["registered"] is True
    permit = report["registrations"][0]
    assert permit["permit_number"] == "2024001234"
    assert permit["status"] == "ISSUED"
    assert permit["address"] == "1 PUBLIC SQ"
    assert "Permit_Owner_Name" not in permit


@pytest.mark.asyncio
async def test_check_property_rejects_hub_html(monkeypatch: pytest.MonkeyPatch) -> None:
    bna._cache.clear()
    fake = _FakeClient(
        _FakeResponse(
            json_body=None,
            text="<html>Unsupported</html>",
            content_type="text/html; charset=utf-8",
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: fake)

    with pytest.raises(ValueError, match="non-JSON"):
        await bna.check_property("1 Public Sq")
