"""Denver, CO — short-term rental licenses (public Colorado open data)."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import address_like_clause, soda_get, source_url

PORTAL = "https://data.colorado.gov"
RESOURCE = "f3vc-vat3"  # City of Denver Short Term Rental Licenses

SPEC = CitySpec(
    code="den",
    name="Denver",
    state="CO",
    service_name="Denver STR License Check",
    tags=("denver", "str", "rental-license", "housing", "diligence"),
    description=(
        "Denver short term rental license check: is this property licensed for "
        "STR? Property due diligence agent for Denver Colorado housing "
        "compliance open data. GET ?address= → short-term rental license number, "
        "status, parcel, expiration. Live Colorado/Denver JSON. Host compliance, "
        "HOA/property manager, agent workflows."
    ),
    sample_address="1945 S GILPIN ST",
    sample_note=(
        "Free fixed-address sample of Denver short-term rental licenses. "
        "Any other Denver address requires payment. Long-term residential "
        "rental licenses are not in this public feed yet."
    ),
    sources_label="Colorado Information Marketplace — Denver Short Term Rental Licenses",
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
        limit=20,
    )
    registrations = [
        {
            "address": r.get("address"),
            "zip": r.get("zip_code"),
            "license_number": r.get("license"),
            "license_type": r.get("license_type"),
            "status": r.get("license_status"),
            "parcel_number": r.get("parcel_number"),
            "expiration_date": r.get("expiration_date"),
            "multiple_licenses": r.get("multiple_licenses"),
        }
        for r in rows
    ]
    active = [
        r
        for r in registrations
        if "active" in (r.get("status") or "").lower()
    ]
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
        violations={
            "total": 0,
            "recent": [],
            "note": "STR license feed only; no code-enforcement join in this product",
        },
        sources=[source_url(PORTAL, RESOURCE)],
        extra={
            "product_scope": "short_term_rental_license",
            "active_licenses": len(active),
        },
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "den",
        "city_name": "Denver",
        "state": "CO",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "str_licensed_active",
        "registered": True,
        "registrations": [
            {
                "address": "1945 S GILPIN ST",
                "license_number": "2019-BFN-0009359",
                "status": "License Issued - Active",
                "expiration_date": "2026-09-24T00:00:00.000",
            }
        ],
        "violation_cases": {"total": 0, "recent": []},
    }
