"""Nashville, TN — short-term rental permits (Metro ArcGIS FeatureServer)."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.city_compliance.models import CitySpec, base_report

# Metro Nashville Residential Short Term Rental Permits (ArcGIS Hub view).
# Do not use data.nashville.gov/resource/*.json — those 200-redirect to Hub HTML.
ARCGIS_URL = (
    "https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services/"
    "Residential_Short_Term_Rental_Permits_view/FeatureServer/0/query"
)

SPEC = CitySpec(
    code="bna",
    name="Nashville",
    state="TN",
    service_name="Nashville STR Permit Check",
    tags=("nashville", "str", "rental-license", "housing", "diligence"),
    description=(
        "Nashville short-term rental permit check: is this property permitted "
        "for STR? Property due diligence agent for Nashville Davidson County "
        "housing compliance open data. GET ?address= → permit number, status, "
        "type. Live Metro Nashville FeatureServer. Host compliance, HOA, agent workflows."
    ),
    sample_address="1 PUBLIC SQ",
    sample_note=(
        "Free fixed-address sample of Nashville short-term rental permits. "
        "Any other Nashville address requires payment."
    ),
    sources_label="Metro Nashville ArcGIS — Residential Short Term Rental Permits",
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _require_feature_server_json(resp: httpx.Response) -> dict[str, Any]:
    """Reject Hub HTML / non-JSON so we never mint a fake unlicensed verdict."""
    ctype = (resp.headers.get("content-type") or "").lower()
    if "json" not in ctype and "javascript" not in ctype:
        raise ValueError(f"Nashville STR feed returned non-JSON ({ctype or 'missing content-type'})")
    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise ValueError("Nashville STR feed is not JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Nashville STR feed JSON is not an object")
    if "error" in data:
        raise RuntimeError(f"Nashville STR FeatureServer error: {data['error']}")
    if "features" not in data:
        raise ValueError("Nashville STR FeatureServer response missing features")
    return data


async def _arcgis_query(address: str) -> list[dict[str, Any]]:
    addr = address.strip().replace("'", "''")
    where = f"UPPER(Address) LIKE '%{addr.upper()}%'"
    params = {
        "where": where,
        "outFields": "Permit__,Permit_Status,Permit_Type,Address,Expiration_Date,Permit_Subtype_Description",
        "f": "json",
        "returnGeometry": "false",
        "resultRecordCount": "20",
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(ARCGIS_URL, params=params)
        resp.raise_for_status()
        data = _require_feature_server_json(resp)
    return [f.get("attributes") or {} for f in data["features"]]


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    rows = await _arcgis_query(address)

    registrations = [
        {
            "address": r.get("Address"),
            "permit_number": r.get("Permit__"),
            "status": r.get("Permit_Status"),
            "permit_type": r.get("Permit_Type"),
            "permit_subtype": r.get("Permit_Subtype_Description"),
            "expiration_date": r.get("Expiration_Date"),
        }
        for r in rows
    ]
    active = [
        r
        for r in registrations
        if "active" in (r.get("status") or "").lower()
        or "issued" in (r.get("status") or "").lower()
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
            "note": "STR permit feed only; no code-enforcement join in this product",
        },
        sources=[ARCGIS_URL],
        extra={
            "product_scope": "short_term_rental_permit",
            "active_licenses": len(active),
        },
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "bna",
        "city_name": "Nashville",
        "state": "TN",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "str_licensed_active",
        "registered": True,
        "registrations": [
            {
                "address": "1 PUBLIC SQ",
                "permit_number": "2024001234",
                "status": "ISSUED",
                "permit_type": "Residential Short Term Rental",
            }
        ],
        "violation_cases": {"total": 0, "recent": []},
    }
