"""San Diego, CA — short-term rental licenses (ArcGIS)."""

from __future__ import annotations

import time
import urllib.parse
from typing import Any
import httpx

from app.city_compliance.models import CitySpec, base_report

# Using the ArcGIS MapServer endpoint for San Diego STRO licenses
ARCGIS_URL = "https://maps.sandiego.gov/server/rest/services/Treasurer/STRO_ACTIVE_LICENSES/MapServer/0/query"

SPEC = CitySpec(
    code="sd",
    name="San Diego",
    state="CA",
    service_name="San Diego STR License Check",
    tags=("sandiego", "str", "rental-license", "housing", "diligence"),
    description=(
        "San Diego short term rental license check: is this property licensed for "
        "STR? Property due diligence agent for San Diego California housing "
        "compliance open data via ArcGIS MapServer. GET ?address= → short-term rental license, "
        "status, tier. Host compliance, HOA/property manager, agent workflows."
    ),
    sample_address="123 MAIN ST",
    sample_note=(
        "Free fixed-address sample of San Diego short-term rental licenses. "
        "Any other San Diego address requires payment."
    ),
    sources_label="San Diego ArcGIS — Active STRO Licenses",
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

async def _arcgis_query(address: str) -> list[dict[str, Any]]:
    # Simple formatting of address for ArcGIS query, may need to handle abbreviations
    addr_upper = address.strip().upper()
    where = f"UPPER(ADDRESS) LIKE '%{addr_upper}%'"
    
    params = {
        "where": where,
        "outFields": "*",
        "f": "json",
        "returnGeometry": "false",
    }
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(ARCGIS_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        
        if "features" not in data:
            return []
            
        return [f.get("attributes", {}) for f in data["features"]]

async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    rows = await _arcgis_query(address)

    registrations = [
        {
            "address": r.get("ADDRESS"),
            "license_number": r.get("LICENSE_ACCOUNT_NO"),
            "license_tier": r.get("LICENSE_TIER"),
            "expiration_date": r.get("EXPIRATION_DATE"),
            "status": "Active", # All items in this dataset are active
        }
        for r in rows
    ]
    
    active = registrations
    
    if active:
        verdict = "str_licensed_active"
    else:
        verdict = "str_unlicensed"

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=registrations,
        violations={"total": 0, "recent": [], "note": "STR license feed only; no code-enforcement join in this product"},
        sources=[ARCGIS_URL],
        extra={"product_scope": "short_term_rental_license", "active_licenses": len(active)},
    )
    _cache[key] = (time.monotonic(), report)
    return report

def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "sd",
        "city_name": "San Diego",
        "state": "CA",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "str_licensed_active",
        "registered": True,
        "registrations": [
            {
                "address": "123 MAIN ST",
                "license_number": "STRO-2023-12345",
                "status": "Active",
                "license_tier": "TIER 3",
            }
        ],
        "violation_cases": {"total": 0, "recent": []},
    }
