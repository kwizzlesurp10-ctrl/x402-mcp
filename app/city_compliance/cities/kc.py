"""Kansas City, MO — open exterior building violations."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import address_like_clause, soda_get, source_url

PORTAL = "https://data.kcmo.org"
RESOURCE = "w5nm-8qv8"  # Open violations - exterior building issues

SPEC = CitySpec(
    code="kc",
    name="Kansas City",
    state="MO",
    service_name="KC Exterior Building Violations",
    tags=("kansascity", "violations", "housing", "property", "code"),
    description=(
        "Does this Kansas City, Missouri address have open exterior building "
        "code violations? Query a street address and get case numbers, "
        "ordinance citations, status, and corrective action from city open "
        "data. For landlord diligence and agent workflows. Input: address "
        "string. Output: JSON, live City of Kansas City open data."
    ),
    sample_address="12100 E 61st Ter",
    sample_note=(
        "Free fixed-address sample of Kansas City open exterior building "
        "violations. Any other KC address requires payment."
    ),
    sources_label="City of Kansas City Open Data — Open exterior building violations",
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    import asyncio
    task_strict = asyncio.create_task(soda_get(
        PORTAL,
        RESOURCE,
        where=address_like_clause("street_address", address),
        limit=40,
    ))
    task_fallback = asyncio.create_task(soda_get(
        PORTAL,
        RESOURCE,
        where=address_like_clause("full_address", address),
        limit=40,
    ))

    rows = await task_strict
    if not rows:
        rows = await task_fallback
    recent = [
        {
            "violation_id": r.get("violationid"),
            "case_number": r.get("casenumber"),
            "case_status": r.get("case_status"),
            "street_address": r.get("street_address") or r.get("full_address"),
            "postal_code": r.get("postalcode"),
            "chapter": r.get("chapter"),
            "ordinance": r.get("ordinance"),
            "description": r.get("description"),
            "vio_status": r.get("vio_status"),
            "corrective_action": r.get("correctiveaction"),
            "date_to_comply": r.get("date_to_comply"),
            "date_resolved": r.get("date_resolved"),
        }
        for r in rows[:25]
    ]
    verdict = "violations_open" if recent else "no_open_violations"
    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=[],
        violations={"total": len(rows), "recent": recent, "open_count": len(recent)},
        sources=[source_url(PORTAL, RESOURCE)],
        extra={"product_scope": "open_exterior_building_violations"},
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "kc",
        "city_name": "Kansas City",
        "state": "MO",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "violations_open",
        "registered": False,
        "registrations": [],
        "violation_cases": {
            "total": 1,
            "open_count": 1,
            "recent": [
                {
                    "case_number": "NPD-2025-03707",
                    "case_status": "Court Case Pending",
                    "ordinance": "56-136",
                }
            ],
        },
    }
