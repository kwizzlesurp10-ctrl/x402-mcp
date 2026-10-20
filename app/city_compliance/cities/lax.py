"""Los Angeles, CA — open Building & Safety code enforcement cases."""

from __future__ import annotations

import re
import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import escape_soda, soda_get, source_url

PORTAL = "https://data.lacity.org"
OPEN_ID = "u82d-eh7z"  # Building and Safety - Code Enforcement Case - Open

SPEC = CitySpec(
    code="lax",
    name="Los Angeles",
    state="CA",
    service_name="LA Code Enforcement Open",
    tags=("losangeles", "code", "violations", "housing", "property"),
    description=(
        "Does this Los Angeles address have open Building & Safety code "
        "enforcement cases? Query street number + street name and get open "
        "case numbers, type, district, and parcel id. For tenant screening "
        "and landlord diligence. Input: address string. Output: JSON, live "
        "LA Open Data."
    ),
    sample_address="1015 S LA BREA AVE",
    sample_note=(
        "Free fixed-address sample of open LA Building & Safety code cases. "
        "Any other Los Angeles address requires payment."
    ),
    sources_label="LA Open Data — Building & Safety Code Enforcement (Open)",
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _parse(address: str) -> tuple[str, str | None, str]:
    raw = re.sub(r"\s+", " ", address.strip().upper())
    m = re.match(
        r"^(\d+)\s+(N|S|E|W)?\s*(.+?)(?:\s+(AVE|AVENUE|ST|STREET|BLVD|RD|DR|WAY|CT|LN|PL))?\.?$",
        raw,
    )
    if not m:
        return "", None, raw
    num, predir, street, _suf = m.group(1), m.group(2), m.group(3).strip(), m.group(4)
    for s in (" AVENUE", " AVE", " STREET", " ST", " BOULEVARD", " BLVD", " ROAD", " RD"):
        if street.endswith(s):
            street = street[: -len(s)].strip()
            break
    return num, predir, street


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    num, predir, street = _parse(address)
    if not num or not street:
        return base_report(
            city=SPEC,
            address=address,
            compliance_verdict="invalid_address",
            registrations=[],
            violations={"total": 0, "recent": []},
            sources=[source_url(PORTAL, OPEN_ID)],
            extra={"parse_error": "need number + street, e.g. 1015 S LA BREA AVE"},
        )

    import asyncio

    where = f"stno='{escape_soda(num)}' AND upper(stname)='{escape_soda(street)}'"
    if predir:
        where_with_dir = where + f" AND upper(predir)='{escape_soda(predir)}'"
        task_strict = asyncio.create_task(soda_get(PORTAL, OPEN_ID, where=where_with_dir, limit=40))
        task_fallback = asyncio.create_task(soda_get(PORTAL, OPEN_ID, where=where, limit=40))
        rows = await task_strict
        if not rows:
            rows = await task_fallback
    else:
        rows = await soda_get(PORTAL, OPEN_ID, where=where, limit=40)

    recent = [
        {
            "case_number": r.get("apno"),
            "case_name": r.get("apname"),
            "street_number": r.get("stno"),
            "predir": r.get("predir"),
            "street_name": r.get("stname"),
            "suffix": r.get("suffix"),
            "zip": r.get("zip"),
            "status": r.get("stat"),
            "type": r.get("aptype"),
            "district": r.get("apc"),
            "parcel_id": r.get("prclid"),
            "opened": r.get("adddttm"),
        }
        for r in rows[:25]
    ]
    verdict = "open_code_cases" if recent else "no_open_code_cases"
    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=[],
        violations={"total": len(rows), "recent": recent, "open_count": len(recent)},
        sources=[source_url(PORTAL, OPEN_ID)],
        extra={
            "product_scope": "open_code_enforcement_cases",
            "parsed": {"number": num, "predir": predir, "street": street},
        },
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "lax",
        "city_name": "Los Angeles",
        "state": "CA",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "open_code_cases",
        "registered": False,
        "registrations": [],
        "violation_cases": {
            "total": 1,
            "open_count": 1,
            "recent": [{"case_number": "119009", "street_name": "LA BREA", "status": "O"}],
        },
    }
