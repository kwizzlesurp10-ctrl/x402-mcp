"""MN property-check paid resource — 402 gate, payment flow, data composition."""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import mn_compliance
from app.config import settings
from app.main import app

client = TestClient(app)

TEST_PAY_TO = "0xTestPayTo00000000000000000000000000000002"


def test_seller_unconfigured_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", None)
    response = client.get("/mn/property-check", params={"address": "1700 Penn Ave N"})
    assert response.status_code == 503
    assert response.json()["error"] == "seller_not_configured"


def test_blank_address_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)
    response = client.get("/mn/property-check", params={"address": "   "})
    assert response.status_code == 422


def test_unpaid_request_returns_402_with_valid_x402_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from x402 import parse_payment_required

    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)
    response = client.get("/mn/property-check", params={"address": "1700 Penn Ave N"})

    assert response.status_code == 402
    assert response.json()["error"] == "payment_required"

    header = response.headers["PAYMENT-REQUIRED"]
    wire = json.loads(base64.b64decode(header))
    parsed = parse_payment_required(wire)
    assert wire["x402Version"] == 2
    assert parsed.accepts, "must offer at least one payment option"
    option = parsed.accepts[0]
    assert option.pay_to == TEST_PAY_TO
    assert option.amount == "10000"  # $0.01 USDC in atomic units
    assert option.network == settings.x402_default_network


def test_402_header_carries_bazaar_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The challenge must be catalogable: resource info + bazaar extension."""
    from x402 import parse_payment_required
    from x402.extensions.bazaar import validate_discovery_extension

    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)
    response = client.get("/mn/property-check", params={"address": "1700 Penn Ave N"})
    assert response.status_code == 402

    wire = json.loads(base64.b64decode(response.headers["PAYMENT-REQUIRED"]))
    parsed = parse_payment_required(wire)

    assert parsed.resource is not None
    assert parsed.resource.url == f"{settings.public_base_url}/mn/property-check"
    assert parsed.resource.mime_type == "application/json"
    assert parsed.resource.description == mn_compliance.RESOURCE_DESCRIPTION

    assert parsed.extensions and "bazaar" in parsed.extensions
    bazaar = parsed.extensions["bazaar"]
    assert bazaar["info"]["input"]["method"] == "GET"
    assert bazaar["info"]["input"]["queryParams"] == {"address": "1700 Penn Ave N"}
    example = bazaar["info"]["output"]["example"]
    assert example["licensed"] is True
    assert example["rental_licenses"][0]["license_number"] == "LIC394217"

    # The facilitator validates info against the extension's own schema
    # before cataloging; a failure here means the product stays invisible.
    validation = validate_discovery_extension(bazaar)
    assert validation.valid, validation.errors


def test_bazaar_discoverable_false_omits_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from x402 import parse_payment_required

    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)
    monkeypatch.setattr(settings, "bazaar_discoverable", False)
    response = client.get("/mn/property-check", params={"address": "1700 Penn Ave N"})
    assert response.status_code == 402

    wire = json.loads(base64.b64decode(response.headers["PAYMENT-REQUIRED"]))
    parsed = parse_payment_required(wire)
    assert parsed.extensions is None
    assert parsed.resource is not None  # resource info still describes the endpoint


def test_paid_request_serves_report_with_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)

    async def fake_settle(signature: str, payment_required: str) -> dict:
        assert signature == "sig-abc"
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0xfeed"},
            "invalid_reason": None,
            "settlement_error": None,
        }

    async def fake_report(address: str) -> dict:
        return {"address_queried": address, "licensed": True}

    monkeypatch.setattr(mn_compliance, "verify_and_settle", fake_settle)
    monkeypatch.setattr(mn_compliance, "check_property", fake_report)

    response = client.get(
        "/mn/property-check",
        params={"address": "1700 Penn Ave N"},
        headers={"PAYMENT-SIGNATURE": "sig-abc"},
    )
    assert response.status_code == 200
    assert response.json()["licensed"] is True
    receipt = json.loads(base64.b64decode(response.headers["PAYMENT-RESPONSE"]))
    assert receipt["success"] is True


def test_invalid_payment_returns_402(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)

    async def fake_settle(signature: str, payment_required: str) -> dict:
        return {
            "is_valid": False,
            "payment_settled": False,
            "settlement": None,
            "invalid_reason": "bad signature",
            "settlement_error": None,
        }

    monkeypatch.setattr(mn_compliance, "verify_and_settle", fake_settle)
    response = client.get(
        "/mn/property-check",
        params={"address": "1700 Penn Ave N"},
        headers={"PAYMENT-SIGNATURE": "nope"},
    )
    assert response.status_code == 402
    assert response.json()["error"] == "payment_invalid"


# ---- data layer against a mock ArcGIS backend -------------------------------

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
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
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


@pytest.mark.asyncio
async def test_check_property_composes_report(mock_arcgis: str) -> None:
    report = await mn_compliance.check_property("1700 Penn Ave N")

    assert report["licensed"] is True
    license_record = report["rental_licenses"][0]
    assert license_record["license_number"] == "LIC394217"
    assert license_record["tier"] == "Tier 1"
    assert license_record["expiration_date"] == "2027-03-01"
    assert report["violation_cases"]["total"] == 1
    assert report["violation_cases"]["recent"][0]["case_number"] == "RS-2025-01"
    assert report["condemned_or_boarded"]["flagged"] is False
    assert "disclaimer" in report
    # owner contact details must never be served
    assert "ownerPhone" not in json.dumps(report)


@pytest.mark.asyncio
async def test_check_property_unknown_address(mock_arcgis: str) -> None:
    report = await mn_compliance.check_property("9999 Nowhere St")
    assert report["licensed"] is False
    assert report["rental_licenses"] == []
    assert report["violation_cases"]["total"] == 0


@pytest.mark.asyncio
async def test_check_property_escapes_quotes(mock_arcgis: str) -> None:
    # An apostrophe in the address must not break the ArcGIS where clause.
    report = await mn_compliance.check_property("100 O'Brien's Way")
    assert report["licensed"] is False


def test_paid_request_records_revenue_ledger_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A settled property-check sale must land in ledger/revenue.jsonl."""
    from app import ledger_io

    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)
    monkeypatch.setattr(ledger_io, "LEDGER", tmp_path)

    async def fake_settle(signature: str, payment_required: str) -> dict:
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0xfeed"},
            "invalid_reason": None,
            "settlement_error": None,
        }

    async def fake_report(address: str) -> dict:
        return {"address_queried": address, "licensed": True}

    monkeypatch.setattr(mn_compliance, "verify_and_settle", fake_settle)
    monkeypatch.setattr(mn_compliance, "check_property", fake_report)

    response = client.get(
        "/mn/property-check",
        params={"address": "1700 Penn Ave N"},
        headers={"PAYMENT-SIGNATURE": "sig-abc"},
    )
    assert response.status_code == 200

    rows = ledger_io.read_ledger_rows("revenue")
    assert len(rows) == 1
    row = rows[0]
    assert row["product_id"] == "mn-property-check"
    assert row["amount_usdc"] == 0.01
    assert row["tx"] == "0xfeed"
    assert row["settled"] is True
