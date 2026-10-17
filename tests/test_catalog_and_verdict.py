"""Catalog placeholders are not buyers, and abated MN cases are not open."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app import demand, ledger_io, mn_compliance
from app.config import settings
from app.swarm import ledger_writer

# The demand suite's external payer. Zero-padded, and still a buyer.
_STRANGER = "0x7e81988b710000000000000000000000000000cd"
# Live cashier only. The rotated-out payer must not become a customer.
_CURRENT_CASHIER = "0x0d25A44f74868eCE53B305C97139CF4B62963410"


def test_abate_and_closed_are_not_open() -> None:
    assert mn_compliance.violation_is_open(
        {"Status_Violation": "Abate", "Status_Violation_Case": "Closed"}
    ) is False
    assert mn_compliance.violation_is_open(
        {"Status_Violation": "Cancel", "Status_Violation_Case": "Cancelled"}
    ) is False
    assert mn_compliance.violation_is_open({"Resolution_Code": "Void"}) is False
    assert mn_compliance.violation_is_open({"Inspection_Result": "Abate"}) is False


def test_enforce_with_a_blank_result_is_open() -> None:
    assert mn_compliance.violation_is_open(
        {"Status_Violation": " ", "Status_Violation_Case": "Enforce"}
    ) is True
    assert mn_compliance.violation_is_open({"Status_Violation_Case": "Open"}) is True
    assert mn_compliance.violation_is_open(
        {"Inspection_Result": "Violations Found"}
    ) is True


def test_catalog_and_buyer_hot_stay_operator_after_rotation() -> None:
    """A wallet rotation must not turn placeholders into external sales."""
    empty: set[str] = set()
    catalog_payer = "0x67ffc9b4390000000000000000000000000000ab"
    assert ledger_io.classify_operator_settle(
        {"tx": "0xcatalog0", "payer": catalog_payer}, empty
    ) is True
    assert ledger_io.classify_operator_settle(
        {"tx": "0xCATALOG2", "payer": catalog_payer}, empty
    ) is True
    assert ledger_io.classify_operator_settle(
        {"tx": "0x" + "11" * 32, "payer": "0x9138fea600000000000000000000000000000001"},
        empty,
    ) is True
    # Not a placeholder and not the buyer-hot key: still unknown with no wallets.
    assert ledger_io.classify_operator_settle(
        {"tx": "0x" + "22" * 32, "payer": _STRANGER}, empty
    ) is None
    assert ledger_io.classify_operator_settle(
        {"tx": "0x" + "33" * 32, "payer": _STRANGER}, {_CURRENT_CASHIER.lower()}
    ) is False


def test_demand_does_not_count_catalog_rows_as_external(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ledger_io, "LEDGER", tmp_path)
    monkeypatch.setattr("app.ledger_store.ledger_store", None)
    monkeypatch.setattr(settings, "operator_wallets", _CURRENT_CASHIER)
    monkeypatch.setattr(demand, "_memory", demand.Counter())
    monkeypatch.setattr(demand, "_memory_last", {})
    monkeypatch.setattr(demand, "_memory_since", "2000-01-01T00:00:00+00:00")
    monkeypatch.setattr(demand, "_memory_clients", {})
    monkeypatch.setattr(demand, "_memory_ua", {})
    monkeypatch.setattr(demand, "_client", lambda: None)

    def _row(tx: str, payer: str) -> None:
        ledger_writer.record_revenue(
            agent_id="seller",
            amount_usdc=0.01,
            network="eip155:8453",
            product_id="mn-property-check",
            tx=tx,
            payer=payer,
        )

    _row("0xcatalog0", "0x67ffc9b4390000000000000000000000000000ab")
    _row("0x" + "44" * 32, "0x9138fea600000000000000000000000000000001")
    _row("0x" + "55" * 32, _STRANGER)
    demand._memory["mn-property-check"] = 100

    report = demand.build_report()
    row = next(
        item for item in report["resources"] if item["resource"] == "mn-property-check"
    )
    assert row["sales_operator"] == 2
    assert row["sales_external"] == 1
    assert row["sales_unknown"] == 0


_LICENSE = {
    "features": [
        {
            "attributes": {
                "address": "1700 PENN AVE N",
                "apn": "1602924320087",
                "licenseNumber": "LIC394217",
                "category": "CONV",
                "tier": "Tier 1",
                "status": "Active",
                "issueDate": 1621814400000,
                "expirationDate": 1803859200000,
                "licensedUnits": "1",
                "ownerName": "EXAMPLE",
                "ward": "5",
                "neighborhoodDesc": "Willard - Hay",
                "communityDesc": "Near North",
                "shortTermRental": "No",
            }
        }
    ]
}


class _ArcGIS(BaseHTTPRequestHandler):
    mode = "abated"

    def do_GET(self) -> None:  # noqa: N802
        if "Active_Rental_Licenses" in self.path:
            body = _LICENSE
        elif "CaseViolations" in self.path:
            if self.mode == "open":
                status_case, status, resolved = "Enforce", " ", None
            else:
                status_case, status, resolved = "Closed", "Abate", 1670544000000
            body = {
                "features": [
                    {
                        "attributes": {
                            "APN": "1602924320087",
                            "Violation_Case_Number": "CE1",
                            "Case_Type": "HIS",
                            "Case_Group": "HISRENTAL",
                            "Status_Violation_Case": status_case,
                            "Violation_Code": "HIS320",
                            "Violation_Code_Description": "Smoke Detectors",
                            "Status_Violation": status,
                            "Resolution_Code": " ",
                            "Processed_Date": 1646179200000,
                            "Resolved_Date": resolved,
                        }
                    }
                ]
            }
        else:
            body = {"features": []}
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


@pytest.fixture()
def arcgis(monkeypatch: pytest.MonkeyPatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ArcGIS)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(
        settings, "mn_data_base_url", f"http://127.0.0.1:{server.server_address[1]}"
    )
    mn_compliance._cache.clear()
    yield server
    mn_compliance._cache.clear()
    server.shutdown()


@pytest.mark.asyncio
async def test_abated_history_is_licensed_clean(arcgis) -> None:
    _ArcGIS.mode = "abated"
    mn_compliance._cache.clear()
    report = await mn_compliance.check_property("1700 Penn Ave N")
    assert report["compliance_verdict"] == "licensed_clean"
    assert report["violation_cases"]["total"] == 1
    assert report["violation_cases"]["open"] == 0
    assert report["violation_cases"]["abated"] == 1
    assert report["violation_cases"]["recent"][0]["inspection_result"] == "Abate"


@pytest.mark.asyncio
async def test_an_open_enforcement_case_is_licensed_with_violations(arcgis) -> None:
    _ArcGIS.mode = "open"
    mn_compliance._cache.clear()
    report = await mn_compliance.check_property("1700 Penn Ave N")
    assert report["compliance_verdict"] == "licensed_with_violations"
    assert report["violation_cases"]["open"] == 1
    assert report["violation_cases"]["abated"] == 0
