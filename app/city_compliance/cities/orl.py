"""Orlando, FL — short-term rental licenses."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import address_like_clause, soda_get, source_url

PORTAL = "https://data.cityoforlando.net"
RESOURCE = "ssrj-rbua"  # Short Term Rental Licenses

SPEC = CitySpec(
    code="orl",
    name="Orlando",
    state="FL",
    service_name="Orlando STR License Check",
    tags=("orlando", "str", "rental", "license", "housing"),
    description=(
        "Does this Orlando address hold a short-term rental license? Query any "
        "street address in Orlando, Florida and get license number, status, "
        "issued/expire dates, and holder name. For host compliance and agent "
        "workflows. Input: address string. Output: JSON, live City of Orlando "
        "open data."
    ),
    sample_address="114 N GLENWOOD AVE",
    sample_note=(
        "Free fixed-address sample of Orlando short-term rental licenses. "
        "Any other Orlando address requires payment."
    ),
    sources_label="City of Orlando Open Data — Short Term Rental Licenses",
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
        where=address_like_clause("property_address", address),
        limit=20,
    )
    registrations = [
        {
            "address": r.get("property_address"),
            "license_number": r.get("license_number"),
            "status": r.get("license_status"),
            "milestone": r.get("license_milestone"),
            "holder_name": r.get("license_holder_name"),
            "license_date": r.get("license_date"),
            "issued_date": r.get("issued_date"),
            "expire_date": r.get("expire_date"),
            "next_renew_date": r.get("next_renew_date"),
            "property_detail": r.get("property_detail"),
        }
        for r in rows
    ]
    # Drop PII-ish fields if present in raw
    active = [r for r in registrations if (r.get("status") or "").lower() == "active"]
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
        violations={"total": 0, "recent": [], "note": "STR license product only"},
        sources=[source_url(PORTAL, RESOURCE)],
        extra={"product_scope": "short_term_rental_license", "active_licenses": len(active)},
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "orl",
        "city_name": "Orlando",
        "state": "FL",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "str_licensed_active",
        "registered": True,
        "registrations": [
            {
                "address": "114 N GLENWOOD AVE",
                "license_number": "STR-1093607",
                "status": "Active",
                "expire_date": "2027-04-15T00:00:00.000",
            }
        ],
        "violation_cases": {"total": 0, "recent": []},
    }
