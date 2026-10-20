"""Philadelphia, PA — L&I property maintenance violations (Carto)."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.carto import escape_sql_literal, sql_query
from app.city_compliance.models import CitySpec, base_report

CARTO = "https://phl.carto.com"
TABLE = "violations"

SPEC = CitySpec(
    code="phi",
    name="Philadelphia",
    state="PA",
    service_name="Philly L&I Violations",
    tags=("philadelphia", "violations", "housing", "property", "code"),
    description=(
        "Does this Philadelphia address have open L&I property maintenance "
        "violations? Query a street address and get violation codes, status, "
        "case numbers, and dates from OpenDataPhilly. For tenant screening and "
        "landlord diligence. Input: address string. Output: JSON, live City of "
        "Philadelphia open data."
    ),
    sample_address="1234 N LEITHGOW ST",
    sample_note=(
        "Free fixed-address sample of Philadelphia L&I violations. "
        "Any other Philadelphia address requires payment."
    ),
    sources_label="OpenDataPhilly / Carto — L&I violations",
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    needle = escape_sql_literal(address.strip().upper())
    # Carto SQL: no NULLS LAST; only select columns confirmed present on `violations`.
    sql = (
        f"SELECT address, violationdate, violationcode, violationstatus, "
        f"casenumber "
        f"FROM {TABLE} "
        f"WHERE upper(address) LIKE '{needle}%' "
        f"ORDER BY violationdate DESC "
        f"LIMIT 40"
    )
    rows = await sql_query(CARTO, sql)
    recent = [
        {
            "address": r.get("address"),
            "violation_date": r.get("violationdate"),
            "code": r.get("violationcode"),
            "status": r.get("violationstatus"),
            "case_number": r.get("casenumber"),
        }
        for r in rows[:25]
    ]
    openish = [v for v in recent if (v.get("status") or "").upper() == "OPEN"]
    if openish:
        verdict = "violations_open"
    elif recent:
        verdict = "violations_closed_only"
    else:
        verdict = "no_violations_found"

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=[],
        violations={"total": len(rows), "recent": recent, "open_count": len(openish)},
        sources=[f"{CARTO}/api/v2/sql (table={TABLE})"],
        extra={"product_scope": "li_property_maintenance_violations"},
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "phi",
        "city_name": "Philadelphia",
        "state": "PA",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "violations_open",
        "registered": False,
        "registrations": [],
        "violation_cases": {
            "total": 1,
            "open_count": 1,
            "recent": [
                {
                    "address": "1234 N LEITHGOW ST",
                    "code": "PM15-302.4",
                    "status": "OPEN",
                    "case_number": "CF-2026-073975",
                }
            ],
        },
    }
