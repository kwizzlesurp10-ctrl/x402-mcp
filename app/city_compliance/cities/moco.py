"""Montgomery County, MD — housing licensing + active code violations."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import address_like_clause, soda_get, source_url

PORTAL = "https://data.montgomerycountymd.gov"
LIC_ID = "et5s-xste"  # Housing Licensing and Registration
VIOL_ID = "8bbt-jrr6"  # Active Housing Code Violations

SPEC = CitySpec(
    code="moco",
    name="Montgomery County",
    state="MD",
    service_name="MoCo Housing License Check",
    tags=("montgomery", "rental-license", "housing", "compliance", "diligence"),
    description=(
        "Is this property licensed in Montgomery County MD? Property due "
        "diligence agent for MoCo housing compliance open data — rental license "
        "status/type/units plus active housing code violations. GET ?address= → "
        "JSON. Tenant screening, landlord diligence (county-wide, not one city)."
    ),
    sample_address="19515 FREDERICK RD",
    sample_note=(
        "Free fixed-address sample of Montgomery County housing licenses "
        "(+ active violations join). Any other MoCo address requires payment."
    ),
    sources_label="Montgomery County Open Data — Housing Licensing + Active Code Violations",
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    lic_rows = await soda_get(
        PORTAL,
        LIC_ID,
        where=address_like_clause("streetaddress", address),
        limit=25,
    )
    viol_rows = await soda_get(
        PORTAL,
        VIOL_ID,
        where=address_like_clause("street_address", address),
        order="date_filed DESC",
        limit=40,
    )
    registrations = [
        {
            "address": r.get("streetaddress"),
            "address_line2": r.get("addressline2"),
            "city": r.get("city"),
            "zip": r.get("zipcode"),
            "license_number": r.get("licensenumber"),
            "license_type": r.get("licensetype"),
            "license_status": r.get("licensestatus"),
            "structure_type": r.get("structuretype"),
            "unit_count": r.get("unitcount"),
            "ownership_type": r.get("ownershiptype"),
            "tax_id": r.get("taxid"),
        }
        for r in lic_rows
    ]
    recent = [
        {
            "case_number": r.get("case_number"),
            "date_filed": r.get("date_filed"),
            "disposition": r.get("disposition"),
            "street_address": r.get("street_address"),
            "city": r.get("city"),
            "zip": r.get("zip_code"),
            "service_request_status": r.get("service_request_status"),
            "violation_id": r.get("violation_id"),
            "corrected": r.get("corrected"),
            "action": r.get("action"),
        }
        for r in viol_rows[:20]
    ]
    active_lic = [
        r
        for r in registrations
        if "active" in (r.get("license_status") or "").lower()
        or "issued" in (r.get("license_status") or "").lower()
    ]
    if active_lic and recent:
        verdict = "licensed_with_violations"
    elif active_lic:
        verdict = "licensed_active"
    elif registrations and recent:
        verdict = "license_inactive_with_violations"
    elif registrations:
        verdict = "license_not_active"
    elif recent:
        verdict = "unlicensed_with_violations"
    else:
        verdict = "no_license_or_active_violations_found"

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=registrations,
        violations={"total": len(viol_rows), "recent": recent, "open_count": len(recent)},
        sources=[source_url(PORTAL, LIC_ID), source_url(PORTAL, VIOL_ID)],
        extra={
            "product_scope": "county_housing_license_and_active_violations",
            "jurisdiction": "Montgomery County, MD",
            "active_licenses": len(active_lic),
        },
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "moco",
        "city_name": "Montgomery County",
        "state": "MD",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "license_not_active",
        "registered": True,
        "registrations": [
            {
                "address": "19515 FREDERICK RD",
                "license_number": "85910",
                "license_status": "Denied",
                "city": "GERMANTOWN",
            }
        ],
        "violation_cases": {"total": 0, "recent": []},
    }
