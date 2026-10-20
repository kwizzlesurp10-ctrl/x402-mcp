"""Atlanta, GA — short-term rental licenses (Placeholder)."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report

SPEC = CitySpec(
    code="atl",
    name="Atlanta",
    state="GA",
    service_name="Atlanta STR License Check",
    tags=("atlanta", "str", "rental-license", "housing", "diligence"),
    description=(
        "Atlanta short term rental license check (placeholder). The city of Atlanta "
        "does not currently publish a stable open data feed for STR licenses. "
        "This endpoint acts as a stub for future integration."
    ),
    sample_address="123 Peachtree St",
    sample_note=(
        "Free fixed-address sample for Atlanta. Returns no data as the city "
        "currently lacks an open data feed for STRs."
    ),
    sources_label="City of Atlanta (No open data feed available)",
    public=False,
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    # Placeholder logic: return unlicensed for everything
    verdict = "str_unlicensed"
    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=[],
        violations={"total": 0, "recent": [], "note": "Atlanta does not currently publish STR data"},
        sources=[],
        extra={"product_scope": "short_term_rental_license", "active_licenses": 0},
    )
    
    _cache[key] = (time.monotonic(), report)
    return report

def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "atl",
        "city_name": "Atlanta",
        "state": "GA",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "str_unlicensed",
        "registered": False,
        "registrations": [],
        "violation_cases": {"total": 0, "recent": []},
    }
