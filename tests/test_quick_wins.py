"""Tests for quick-win enhancements: cache, logging, quota auth."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app import mn_compliance
from app.config import settings
from app.main import app

client = TestClient(app)


# ---- MN property-check cache ------------------------------------------------


@pytest.mark.asyncio
async def test_cache_returns_same_object(mock_arcgis: str) -> None:
    """Second call for the same address should return cached data (no ArcGIS hit)."""
    mn_compliance._cache.clear()
    first = await mn_compliance.check_property("1700 Penn Ave N")
    second = await mn_compliance.check_property("1700 Penn Ave N")
    assert first is second  # exact same dict object from cache


@pytest.mark.asyncio
async def test_cache_key_is_normalised(mock_arcgis: str) -> None:
    """Lookups differing only in case / whitespace share the cache."""
    mn_compliance._cache.clear()
    first = await mn_compliance.check_property("1700 penn ave n")
    second = await mn_compliance.check_property("  1700 PENN AVE N  ")
    assert first is second


@pytest.mark.asyncio
async def test_cache_expires(mock_arcgis: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Entries older than _CACHE_TTL are evicted."""
    mn_compliance._cache.clear()
    first = await mn_compliance.check_property("1700 Penn Ave N")
    # Pretend the entry was written 20 minutes ago
    key = list(mn_compliance._cache.keys())[0]
    ts, data = mn_compliance._cache[key]
    mn_compliance._cache[key] = (ts - 1200, data)
    second = await mn_compliance.check_property("1700 Penn Ave N")
    assert first is not second  # fresh fetch


# ---- Structured JSON logging ------------------------------------------------


def test_json_log_output(capfd: pytest.CaptureFixture) -> None:
    """Log lines must be parseable JSON with required fields."""
    from app.logging_config import JSONFormatter, setup_logging

    setup_logging()
    logger = logging.getLogger("x402.test")
    logger.info("test message", extra={"tool": "discover_services"})

    captured = capfd.readouterr().out.strip().split("\n")
    # Find our line (there may be others)
    entries = [json.loads(l) for l in captured if "test message" in l]
    assert len(entries) >= 1
    entry = entries[0]
    assert entry["level"] == "INFO"
    assert entry["msg"] == "test message"
    assert entry["tool"] == "discover_services"
    assert "ts" in entry


# ---- /quota auth -------------------------------------------------------------


def test_quota_open_when_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """When OPERATOR_TOKEN is unset, /quota is accessible without auth."""
    monkeypatch.setattr(settings, "operator_token", None)
    resp = client.get("/quota/test-agent")
    assert resp.status_code == 200


def test_quota_rejects_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "operator_token", "s3cret")
    resp = client.get("/quota/test-agent")
    assert resp.status_code == 401


def test_quota_rejects_wrong_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "operator_token", "s3cret")
    resp = client.get("/quota/test-agent", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_quota_accepts_correct_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "operator_token", "s3cret")
    resp = client.get("/quota/test-agent", headers={"Authorization": "Bearer s3cret"})
    assert resp.status_code == 200
    assert "meta" in resp.json()


# ---- Fixtures (shared with test_mn_compliance) --------------------------------

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

_LICENSES = {
    "features": [
        {
            "attributes": {
                "address": "1700 PENN AVE N",
                "apn": "1602924310042",
                "licenseNumber": "LIC394217",
                "category": "CONV",
                "tier": "Tier 1",
                "status": "Active",
                "issueDate": 1740000000000,
                "expirationDate": 1803859200000,
                "licensedUnits": 1,
                "ownerName": "EXAMPLE LLC",
                "ward": "5",
                "neighborhoodDesc": "Willard - Hay",
                "communityDesc": "Near North",
                "shortTermRental": "No",
            }
        }
    ]
}
_VIOLATIONS = {
    "features": [
        {
            "attributes": {
                "APN": "1602924310042",
                "Violation_Case_Number": "RS-2025-01",
                "Case_Type": "Rental License",
                "Case_Group": "Housing",
                "Inspection_Result": "Violations Found",
                "Inspection_Type_Desc": "Initial Inspection",
                "Start_Date": 1735689600000,
                "Completed_Date": 1738368000000,
            }
        }
    ]
}
_CONDEMNED: dict = {"features": []}


class _MockArcGIS(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        where = parse_qs(parsed.query).get("where", [""])[0]
        if "Active_Rental_Licenses" in parsed.path:
            body = _LICENSES if "1700 PENN" in where else {"features": []}
        elif "CaseViolations" in parsed.path:
            body = _VIOLATIONS
        elif "Condemned_by_Boarding" in parsed.path:
            body = _CONDEMNED
        else:
            body = {"error": {"code": 404, "message": "unknown dataset"}}
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture()
def mock_arcgis(monkeypatch: pytest.MonkeyPatch) -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockArcGIS)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "mn_data_base_url", f"http://127.0.0.1:{port}")
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
