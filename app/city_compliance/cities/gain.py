"""Gainesville, FL — code complaints, violations & permits."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import address_like_clause, soda_get, source_url

PORTAL = "https://data.cityofgainesville.org"
RESOURCE = "vu9p-a5f7"  # Code Complaints, Violations & Permits

SPEC = CitySpec(
    code="gain",
    name="Gainesville",
    state="FL",
    service_name="Gainesville Code Cases",
    tags=("gainesville", "code", "violations", "housing", "property"),
    description=(
        "Does this Gainesville, Florida address have open code enforcement "
        "cases? Query a street address and get case numbers, types, status, "
        "and parcel from city open data. For landlord diligence and agent "
        "workflows. Input: address string. Output: JSON, live City of "
        "Gainesville open data."
    ),
    sample_address="0 W 1ST ST",
    sample_note=(
        "Free fixed-address sample of Gainesville code cases. "
        "Any other Gainesville address requires payment."
    ),
    sources_label="City of Gainesville Open Data — Code Complaints, Violations & Permits",
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    rows = await soda_get(
        PORTAL,
        RESOURCE,
        where=address_like_clause("address", address),
        limit=40,
    )
    recent = [
        {
            "case_number": r.get("number"),
            "parcel": r.get("parcel"),
            "case_type": r.get("case_type"),
            "address": r.get("address"),
            "status": r.get("status"),
            "infraction": r.get("infraction"),
            "outstanding_inspection": r.get("outstanding_inspection"),
            "inspector": r.get("inspector"),
        }
        for r in rows[:25]
    ]
    openish = [
        v
        for v in recent
        if (v.get("status") or "").lower() not in {"closed", "close", "completed"}
    ]
    if openish:
        verdict = "cases_open"
    elif recent:
        verdict = "cases_closed_only"
    else:
        verdict = "no_cases_found"

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=[],
        violations={"total": len(rows), "recent": recent, "open_count": len(openish)},
        sources=[source_url(PORTAL, RESOURCE)],
        extra={"product_scope": "code_complaints_violations_permits"},
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "gain",
        "city_name": "Gainesville",
        "state": "FL",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "cases_closed_only",
        "registered": False,
        "registrations": [],
        "violation_cases": {
            "total": 1,
            "open_count": 0,
            "recent": [{"case_number": "CE-11-00749", "status": "Closed", "case_type": "Property Maintenance"}],
        },
    }
