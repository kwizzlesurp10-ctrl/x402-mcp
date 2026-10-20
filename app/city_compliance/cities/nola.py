"""New Orleans, LA — active short-term rental licenses."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import address_like_clause, soda_get, source_url

PORTAL = "https://data.nola.gov"
RESOURCE = "ufdg-ajws"  # Active Short-Term Rental Licenses

SPEC = CitySpec(
    code="nola",
    name="New Orleans",
    state="LA",
    service_name="NOLA STR License Check",
    tags=("neworleans", "str", "rental", "license", "housing"),
    description=(
        "Does this New Orleans address hold an active short-term rental license? "
        "Query any street address and get license number, type, subtype, "
        "expiration, and operator/holder fields from city open data. For host "
        "compliance and agent workflows. Input: address string. Output: JSON, "
        "live City of New Orleans open data."
    ),
    sample_address="179 Dunleith Dr",
    sample_note=(
        "Free fixed-address sample of New Orleans active STR licenses. "
        "Any other New Orleans address requires payment."
    ),
    sources_label="City of New Orleans Open Data — Active Short-Term Rental Licenses",
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
        limit=25,
    )
    registrations = [
        {
            "address": r.get("address"),
            "license_number": r.get("license_number"),
            "license_type": r.get("license_type"),
            "residential_subtype": r.get("residential_subtype"),
            "expiration_date": r.get("expiration_date"),
            "issue_date": r.get("issue_date"),
            "application_date": r.get("application_date"),
            "holder_name": r.get("license_holder_name"),
            "operator_name": r.get("operator_name"),
            "bedroom_limit": r.get("bedroom_limit"),
            "guest_occupancy_limit": r.get("guest_occupancy_limit"),
            "record_url": (r.get("link") or {}).get("url")
            if isinstance(r.get("link"), dict)
            else r.get("link"),
        }
        for r in rows
    ]
    verdict = "str_licensed_active" if registrations else "str_unlicensed"
    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=registrations,
        violations={"total": 0, "recent": [], "note": "STR license product only"},
        sources=[source_url(PORTAL, RESOURCE)],
        extra={"product_scope": "short_term_rental_license", "active_licenses": len(registrations)},
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "nola",
        "city_name": "New Orleans",
        "state": "LA",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "str_licensed_active",
        "registered": True,
        "registrations": [
            {
                "address": "179 Dunleith Dr",
                "license_number": "20-OSTR-00670",
                "license_type": "Short Term Rental Operator",
            }
        ],
        "violation_cases": {"total": 0, "recent": []},
    }
