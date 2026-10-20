"""Austin, TX — short-term rental licenses (Socrata)."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import address_like_clause, soda_get, source_url

PORTAL = "https://data.austintexas.gov"
RESOURCE = "2fah-4p7e"

SPEC = CitySpec(
    code="atx",
    name="Austin",
    state="TX",
    service_name="Austin STR License Check",
    tags=("austin", "str", "rental-license", "housing", "diligence"),
    description=(
        "Austin short term rental license check: is this property licensed for "
        "STR? Property due diligence agent for Austin Texas housing "
        "compliance open data. GET ?address= → short-term rental license, "
        "status. Live Austin JSON. Host compliance, HOA/property manager, agent workflows."
    ),
    sample_address="1108 Lavaca St",
    sample_note=(
        "Free fixed-address sample of Austin short-term rental licenses. "
        "Any other Austin address requires payment."
    ),
    sources_label="Austin Open Data — Short Term Rental Locations",
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
        where=address_like_clause("prop_address", address),
        limit=20,
    )
    if not rows:
        rows = []

    registrations = [
        {
            "address": r.get("prop_address") or r.get("address"),
            "license_number": r.get("case_number") or r.get("license_number") or r.get("license"),
            "status": r.get("license_status") or r.get("status"),
            "issue_date": r.get("issue_date"),
        }
        for r in rows
    ]
    active = [r for r in registrations if "active" in (r.get("status") or "").lower()]
    
    if active:
        verdict = "str_licensed_active"
    elif registrations:
        verdict = "str_licensed_inactive"
    else:
        verdict = "str_unlicensed"

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=registrations,
        violations={"total": 0, "recent": [], "note": "STR license feed only; no code-enforcement join in this product"},
        sources=[source_url(PORTAL, RESOURCE)],
        extra={"product_scope": "short_term_rental_license", "active_licenses": len(active)},
    )
    _cache[key] = (time.monotonic(), report)
    return report

def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "atx",
        "city_name": "Austin",
        "state": "TX",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "str_licensed_active",
        "registered": True,
        "registrations": [
            {
                "address": "1108 LAVACA ST",
                "license_number": "OL2013-101111",
                "status": "Active",
            }
        ],
        "violation_cases": {"total": 0, "recent": []},
    }
