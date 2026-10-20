"""Miami, FL — short-term rental licenses (ArcGIS)."""

from __future__ import annotations

import time
import urllib.parse
from typing import Any
import httpx

from app.city_compliance.models import CitySpec, base_report

# Placeholder URL for Miami Certificate of Use as an explicit open data layer wasn't easily found
# We'll use a stub that queries the Miami-Dade County Open Data Hub MapServer as an example
# In production, this would point to the exact CU layer
ARCGIS_URL = "https://gis.miamidade.gov/arcgis/rest/services/LandManagement/MD_ZoningLandManagementViewer/MapServer/0/query"

SPEC = CitySpec(
    code="mia",
    name="Miami",
    state="FL",
    service_name="Miami STR/Certificate of Use Check",
    tags=("miami", "str", "rental-license", "certificate-of-use", "housing", "diligence"),
    description=(
        "Miami short term rental / Certificate of Use check (placeholder): is this property licensed for "
        "STR? Property due diligence agent for Miami Florida housing "
        "compliance open data via ArcGIS MapServer. GET ?address= → short-term rental license, "
        "status."
    ),
    sample_address="123 OCEAN DR",
    sample_note=(
        "Free fixed-address sample of Miami short-term rental licenses. "
        "Any other Miami address requires payment."
    ),
    sources_label="Miami ArcGIS — Certificates of Use (Placeholder)",
    public=False,
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

async def _arcgis_query(address: str) -> list[dict[str, Any]]:
    # This is a placeholder since the actual CU open data layer wasn't found
    return []

async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    rows = await _arcgis_query(address)

    registrations = [
        {
            "address": r.get("ADDRESS"),
            "license_number": r.get("CU_NUMBER"),
            "status": r.get("STATUS"),
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
        sources=[ARCGIS_URL],
        extra={"product_scope": "short_term_rental_license", "active_licenses": len(active)},
    )
    _cache[key] = (time.monotonic(), report)
    return report

def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "mia",
        "city_name": "Miami",
        "state": "FL",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "str_licensed_active",
        "registered": True,
        "registrations": [
            {
                "address": "123 OCEAN DR",
                "license_number": "CU-2023-9999",
                "status": "Active",
            }
        ],
        "violation_cases": {"total": 0, "recent": []},
    }
