"""Decision-ready fields on US city property-check reports."""

from __future__ import annotations

import pytest

from app.city_compliance import decision, publish, registry
from app.city_compliance.decision import (
    VERDICT_EXPIRED,
    VERDICT_FLAGGED,
    VERDICT_LICENSED,
    VERDICT_NO_VIOLATIONS_FOUND,
    VERDICT_NOT_LICENSED,
    VERDICT_UNKNOWN,
    VERDICT_VIOLATIONS_OPEN,
)


def _minimal_report(compliance_verdict: str, **extra: object) -> dict:
    base = {
        "city": "sea",
        "city_name": "Seattle",
        "state": "WA",
        "address_queried": "1531 BELMONT AVE",
        "compliance_verdict": compliance_verdict,
        "registrations": [],
        "registered": False,
        "violation_cases": {"total": 0, "recent": []},
        "sources": ["https://data.seattle.gov/resource/j2xh-c7vt.json"],
        "generated_at": "2026-11-04T12:00:00+00:00",
        "network_product": "us-city-open-data-compliance",
    }
    base.update(extra)
    return base


def test_normalized_verdict_maps_active_str_license() -> None:
    report = _minimal_report(
        "str_licensed_active",
        registered=True,
        registrations=[{"address": "1531 BELMONT AVE", "status": "Active"}],
    )
    enriched = decision.enrich_decision(report)
    assert enriched["verdict"] == VERDICT_LICENSED
    assert enriched["compliance_verdict"] == "str_licensed_active"
    assert enriched["summary"]
    assert enriched["confidence"] in ("high", "medium", "low")
    assert enriched["data_as_of"] == "2026-11-04T12:00:00+00:00"
    assert enriched["source_url"].startswith("https://")
    assert "registrations" in enriched["records"]


def test_expired_registration_maps_to_expired_verdict() -> None:
    report = _minimal_report(
        "registered_inactive",
        registrations=[{"status": "Expired", "address": "1 MAIN ST"}],
    )
    assert decision.normalized_verdict("registered_inactive", report) == VERDICT_EXPIRED


def test_open_violations_override_clean_license_token() -> None:
    report = _minimal_report(
        "licensed_clean",
        city="mn",
        registered=True,
        violation_cases={"total": 2, "open": 1, "recent": []},
    )
    assert (
        decision.normalized_verdict(
            "licensed_clean", report, product_mode="license_and_violations"
        )
        == VERDICT_VIOLATIONS_OPEN
    )


def test_condemned_maps_to_flagged() -> None:
    report = _minimal_report("condemned_or_boarded")
    assert decision.normalized_verdict("condemned_or_boarded", report) == VERDICT_FLAGGED


def test_violation_only_city_open() -> None:
    report = _minimal_report(
        "violations_open",
        city="chi",
        violation_cases={"total": 3, "open": 2, "recent": []},
    )
    assert (
        decision.normalized_verdict(
            "violations_open", report, product_mode="violations_only"
        )
        == VERDICT_VIOLATIONS_OPEN
    )


def test_unknown_when_no_signals() -> None:
    report = {"address_queried": "x", "compliance_verdict": "custom_city_token"}
    assert decision.normalized_verdict("custom_city_token", report) == VERDICT_UNKNOWN


def test_invalid_address_is_unknown() -> None:
    report = _minimal_report("invalid_address")
    assert decision.normalized_verdict("invalid_address", report) == VERDICT_UNKNOWN


def test_key_dates_from_registration() -> None:
    report = _minimal_report(
        "str_licensed_active",
        registrations=[
            {
                "address": "1945 S GILPIN ST",
                "issue_date": "2019-01-01",
                "expiration_date": "2026-09-24",
                "status": "Active",
            }
        ],
    )
    dates = decision.key_dates(report)
    assert dates["issued"] == "2019-01-01"
    assert dates["expires"] == "2026-09-24"


CITY_VERDICT_FIXTURES: list[tuple[str, str, str]] = [
    ("mn", "licensed_clean", VERDICT_LICENSED),
    ("mn", "unlicensed", VERDICT_NOT_LICENSED),
    ("mn", "licensed_with_violations", VERDICT_VIOLATIONS_OPEN),
    ("sea", "registered_active", VERDICT_LICENSED),
    ("sea", "unregistered", VERDICT_NOT_LICENSED),
    ("den", "str_licensed_active", VERDICT_LICENSED),
    ("den", "str_unlicensed", VERDICT_NOT_LICENSED),
    ("nyc", "registered_clean", VERDICT_LICENSED),
    ("chi", "violations_open", VERDICT_VIOLATIONS_OPEN),
    ("sf", "nov_historical_only", VERDICT_NO_VIOLATIONS_FOUND),
    ("phi", "no_violations_found", VERDICT_NO_VIOLATIONS_FOUND),
    ("bos", "violations_closed_only", VERDICT_NO_VIOLATIONS_FOUND),
    ("orl", "str_licensed_inactive", VERDICT_EXPIRED),
    ("moco", "license_not_active", VERDICT_EXPIRED),
    ("gain", "cases_open", VERDICT_VIOLATIONS_OPEN),
    ("kc", "violations_open", VERDICT_VIOLATIONS_OPEN),
    ("lax", "open_code_cases", VERDICT_VIOLATIONS_OPEN),
    ("atx", "str_licensed_active", VERDICT_LICENSED),
    ("bna", "str_unlicensed", VERDICT_NOT_LICENSED),
    ("nola", "str_unlicensed", VERDICT_NOT_LICENSED),
    ("sd", "str_licensed_active", VERDICT_LICENSED),
    ("atl", "str_unlicensed", VERDICT_UNKNOWN),
    ("mia", "str_licensed_inactive", VERDICT_UNKNOWN),
]


@pytest.mark.parametrize(("code", "compliance", "expected"), CITY_VERDICT_FIXTURES)
def test_each_city_compliance_token_maps(code: str, compliance: str, expected: str) -> None:
    mod = registry.get_city(code)
    spec = mod.SPEC
    report = _minimal_report(
        compliance,
        city=spec.code,
        city_name=spec.name,
        state=spec.state,
    )
    if compliance == "licensed_with_violations":
        report["violation_cases"] = {"total": 1, "open": 1, "recent": []}
        report["registered"] = True
    if compliance == "violations_open":
        report["violation_cases"] = {"total": 1, "open": 1, "recent": []}
    if compliance in ("nov_historical_only", "violations_closed_only", "no_violations_found"):
        report["violation_cases"] = {"total": 1, "open": 0, "recent": []}
    out = publish.prepare_city_report(report, spec=spec, address_fallback="1 Test St")
    assert out["verdict"] == expected
    assert out["product_mode"]
    assert out["coverage_note"]
    assert out["summary"]
    assert "records" in out
    assert out["compliance_verdict"] == compliance


def test_open_violation_count_reads_adapter_aliases() -> None:
    assert (
        decision.open_violation_count(
            {"violation_cases": {"total": 3, "open_count": 2, "recent": []}}
        )
        == 2
    )
    assert (
        decision.open_violation_count(
            {"violation_cases": {"total": 1, "openish_count": 1, "recent": []}}
        )
        == 1
    )


def test_moco_openish_count_surfaces_violations_open_verdict() -> None:
    mod = registry.get_city("moco")
    report = _minimal_report(
        "licensed_with_violations",
        city="moco",
        registered=True,
        registrations=[{"status": "Active", "address": "1 Main"}],
        violation_cases={"total": 2, "openish_count": 1, "recent": []},
    )
    out = publish.prepare_city_report(report, spec=mod.SPEC, address_fallback="1 Main")
    assert out["verdict"] == VERDICT_VIOLATIONS_OPEN
    assert out["open_violations_count"] == 1


def test_best_registration_skips_inactive_before_active() -> None:
    report = _minimal_report(
        "registered_active",
        registered=True,
        registrations=[
            {
                "status": "Inactive Registration",
                "expiration_date": "2020-01-01",
                "address": "1531 BELMONT AVE",
            },
            {
                "status": "Active Registration",
                "expiration_date": "2027-04-21",
                "address": "1531 BELMONT AVE",
            },
        ],
    )
    dates = decision.key_dates(report)
    assert dates["expires"] == "2027-04-21"


def test_nyc_and_orlando_registration_date_fields() -> None:
    nyc = {
        "registrations": [
            {
                "last_registration_date": "2024-06-01",
                "registration_end_date": "2026-06-01",
            }
        ]
    }
    assert decision.key_dates(nyc)["issued"] == "2024-06-01"
    assert decision.key_dates(nyc)["expires"] == "2026-06-01"
    orl = {
        "registrations": [
            {
                "issued_date": "2023-01-15",
                "expire_date": "2025-01-15",
                "status": "active",
            }
        ]
    }
    assert decision.key_dates(orl)["issued"] == "2023-01-15"
    assert decision.key_dates(orl)["expires"] == "2025-01-15"


def test_chi_enforcement_only_never_not_licensed_with_registered_false() -> None:
    mod = registry.get_city("chi")
    out = publish.prepare_city_report(
        _minimal_report(
            "no_violations_found",
            city="chi",
            registered=False,
            violation_cases={"total": 0, "recent": []},
        ),
        spec=mod.SPEC,
        address_fallback="121 N LaSalle St",
    )
    assert out["verdict"] == VERDICT_NO_VIOLATIONS_FOUND
    assert out["verdict"] != VERDICT_NOT_LICENSED
    assert out["product_mode"] == "violations_only"


def test_sample_route_includes_decision_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    code = "sea"
    mod = registry.get_city(code)

    async def fake_report(address: str) -> dict:
        return _minimal_report(
            "registered_active",
            registered=True,
            registrations=[{"address": address, "status": "Active Registration"}],
        )

    monkeypatch.setattr(mod, "check_property", fake_report)
    response = client.get(f"/us/{code}/property-check/sample")
    assert response.status_code == 200
    report = response.json()["report"]
    assert report["verdict"] == VERDICT_LICENSED
    assert report["open_violations_count"] == 0
