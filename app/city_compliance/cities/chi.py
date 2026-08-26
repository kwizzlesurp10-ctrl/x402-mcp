"""Chicago, IL — building code violations by address (open data)."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import address_like_clause, soda_get, source_url

PORTAL = "https://data.cityofchicago.org"
# Building Violations (primary address field varies; try `address`)
VIOL_ID = "22u3-xenr"

SPEC = CitySpec(
    code="chi",
    name="Chicago",
    state="IL",
    service_name="Chicago Building Violations",
    tags=("chicago", "building", "violations", "housing", "diligence"),
    description=(
        "Chicago building violations address check: open DOB code cases for a "
        "street address. Property due diligence agent for Chicago Illinois "
        "housing compliance open data. GET ?address= → recent building "
        "violations with codes, status, inspector comments (JSON). Tenant "
        "screening, landlord diligence, lending. Note: citywide rental-license "
        "registry is not a single open feed."
    ),
    sample_address="7840 S WESTERN AVE",
    sample_note=(
        "Free fixed-address sample of Chicago building violations. "
        "Any other Chicago address requires payment."
    ),
    sources_label="City of Chicago Open Data — Building Violations",
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    # Chicago building violations: primary address column is `address`
    rows = await soda_get(
        PORTAL,
        VIOL_ID,
        where=address_like_clause("address", address),
        order="violation_date DESC",
        limit=40,
    )
    if not rows:
        # Some rows only put address in violation_location
        rows = await soda_get(
            PORTAL,
            VIOL_ID,
            where=address_like_clause("violation_location", address),
            order="violation_date DESC",
            limit=40,
        )

    recent = [
        {
            "id": r.get("id"),
            "violation_date": r.get("violation_date"),
            "code": r.get("violation_code"),
            "status": r.get("violation_status"),
            "description": r.get("violation_description"),
            "location": r.get("violation_location") or r.get("address"),
            "inspector_comments": r.get("violation_inspector_comments"),
            "ordinance": r.get("violation_ordinance"),
        }
        for r in rows[:20]
    ]
    open_rows = [v for v in recent if (v.get("status") or "").upper() == "OPEN"]

    if open_rows:
        verdict = "violations_open"
    elif recent:
        verdict = "violations_closed_only"
    else:
        verdict = "no_violations_found"

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=[],  # no citywide rental license open feed
        violations={"total": len(rows), "recent": recent, "open_count": len(open_rows)},
        sources=[source_url(PORTAL, VIOL_ID)],
        extra={
            "product_scope": "building_code_violations",
            "rental_license_note": (
                "Chicago does not publish a complete long-term rental license "
                "registry comparable to Minneapolis; this product is violation-centric."
            ),
        },
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "chi",
        "city_name": "Chicago",
        "state": "IL",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "violations_open",
        "registered": False,
        "registrations": [],
        "violation_cases": {
            "total": 1,
            "open_count": 1,
            "recent": [
                {
                    "code": "CN193110",
                    "status": "OPEN",
                    "description": "VACANT BUILDING - REGISTER",
                }
            ],
        },
    }
