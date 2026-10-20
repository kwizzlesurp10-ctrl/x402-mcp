"""Boston, MA — building and property violations (CKAN datastore)."""

from __future__ import annotations

import re
import time
from typing import Any

from app.city_compliance.ckan import datastore_search, resource_page
from app.city_compliance.models import CitySpec, base_report

PORTAL = "https://data.boston.gov"
RESOURCE_ID = "800a2663-1d6a-46e7-9356-bedb70f5332c"
DATASET_SLUG = "building-and-property-violations1"

SPEC = CitySpec(
    code="bos",
    name="Boston",
    state="MA",
    service_name="Boston Property Violations",
    tags=("boston", "violations", "housing", "property", "code"),
    description=(
        "Does this Boston address have building and property code violations? "
        "Query street number + street name and get case numbers, codes, "
        "status, and descriptions from Analyze Boston. For tenant screening "
        "and landlord diligence. Input: address string. Output: JSON, live "
        "City of Boston open data."
    ),
    sample_address="302 Sumner ST East Boston",
    sample_note=(
        "Free fixed-address sample of Boston building/property violations. "
        "Any other Boston address requires payment."
    ),
    sources_label="Analyze Boston — Building and Property Violations",
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _parse(address: str) -> tuple[str, str]:
    raw = re.sub(r"\s+", " ", address.strip())
    # Drop neighborhood suffixes for filter (East Boston, etc.)
    for hood in (
        " EAST BOSTON",
        " SOUTH BOSTON",
        " DORCHESTER",
        " ROXBURY",
        " JAMAICA PLAIN",
        " BRIGHTON",
        " ALLSTON",
        " CHARLESTOWN",
        " HYDE PARK",
        " ROSLINDALE",
        " WEST ROXBURY",
        " MATTAPAN",
        " BOSTON",
    ):
        if raw.upper().endswith(hood):
            raw = raw[: -len(hood)].strip()
            break
    m = re.match(
        r"^(\d+[A-Z\-]?)\s+(.+?)(?:\s+(ST|STREET|AVE|AVENUE|BLVD|RD|DR|WAY|CT|LN|PL))?\.?$",
        raw,
        re.I,
    )
    if not m:
        return "", raw.upper()
    num = m.group(1)
    street = m.group(2).strip()
    # Boston street field is often title case without suffix (Sumner)
    for s in (" Street", " St", " Avenue", " Ave", " Boulevard", " Blvd", " Road", " Rd"):
        if street.lower().endswith(s.lower()):
            street = street[: -len(s)].strip()
            break
    # Datastore stores title-ish names; try both Title and UPPER via q fallback
    return num, street.title() if street.isupper() else street


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    num, street = _parse(address)
    if not num or not street:
        return base_report(
            city=SPEC,
            address=address,
            compliance_verdict="invalid_address",
            registrations=[],
            violations={"total": 0, "recent": []},
            sources=[resource_page(PORTAL, DATASET_SLUG)],
            extra={"parse_error": "need number + street, e.g. 302 Sumner ST"},
        )

    import asyncio
    task_strict = asyncio.create_task(datastore_search(
        PORTAL,
        RESOURCE_ID,
        filters={"violation_stno": num, "violation_street": street},
        limit=40,
    ))
    task_fallback = asyncio.create_task(datastore_search(
        PORTAL, RESOURCE_ID, q=f"{num} {street}", limit=40
    ))

    rows = await task_strict
    if not rows:
        # Case-insensitive-ish fallback via free text
        fallback_rows = await task_fallback
        rows = [
            r
            for r in fallback_rows
            if str(r.get("violation_stno") or "") == num
            and street.upper() in str(r.get("violation_street") or "").upper()
        ]

    recent = [
        {
            "case_no": r.get("case_no"),
            "status": r.get("status"),
            "code": r.get("code"),
            "description": r.get("description"),
            "street_number": r.get("violation_stno"),
            "street": r.get("violation_street"),
            "suffix": r.get("violation_suffix"),
            "city": r.get("violation_city"),
            "zip": r.get("violation_zip"),
            "status_dttm": r.get("status_dttm"),
            "sam_id": r.get("sam_id"),
        }
        for r in rows[:25]
    ]
    openish = [v for v in recent if (v.get("status") or "").lower() not in {"closed", "close"}]
    if openish:
        verdict = "violations_open"
    elif recent:
        verdict = "violations_closed_only"
    else:
        verdict = "no_violations_found"

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=[],
        violations={"total": len(rows), "recent": recent, "open_count": len(openish)},
        sources=[resource_page(PORTAL, DATASET_SLUG)],
        extra={"product_scope": "building_property_violations", "parsed": {"number": num, "street": street}},
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "bos",
        "city_name": "Boston",
        "state": "MA",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "violations_closed_only",
        "registered": False,
        "registrations": [],
        "violation_cases": {
            "total": 1,
            "open_count": 0,
            "recent": [{"case_no": "V91983", "status": "Closed", "description": "Unsafe and Dangerous"}],
        },
    }
