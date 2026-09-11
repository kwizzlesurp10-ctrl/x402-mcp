"""San Francisco, CA — DBI Notices of Violation (Housing Inspection)."""

from __future__ import annotations

import re
import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import escape_soda, soda_get, source_url

PORTAL = "https://data.sf.gov"
NOV_ID = "nbtm-fbw5"  # Notices of Violation issued by DBI

SPEC = CitySpec(
    code="sf",
    name="San Francisco",
    state="CA",
    service_name="SF Housing NOV Check",
    tags=("sanfrancisco", "housing", "violations", "dbi", "property"),
    description=(
        "Does this San Francisco address have Department of Building Inspection "
        "notices of violation? Query house number + street and get NOV status, "
        "category, filing date, and division. For tenant screening, landlord "
        "diligence, and lending checks. Input: address string. Output: JSON, "
        "live SF Open Data."
    ),
    sample_address="2329 Mission St",
    sample_note=(
        "Free fixed-address sample of SF DBI Notices of Violation. "
        "Any other San Francisco address requires payment."
    ),
    sources_label="SF Open Data — DBI Notices of Violation",
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _parse(address: str) -> tuple[str, str]:
    raw = re.sub(r"\s+", " ", address.strip())
    m = re.match(
        r"^(\d+[A-Z\-]?)\s+(.+?)(?:\s+(ST|STREET|AVE|AVENUE|BLVD|RD|ROAD|DR|WAY|CT|LN|PL|TER))?\.?$",
        raw,
        re.I,
    )
    if not m:
        return "", raw.upper()
    num, street, suf = m.group(1), m.group(2).strip(), m.group(3)
    # SF street_name is often without suffix (e.g. Mission not Mission St)
    street_core = street.upper()
    for s in (" STREET", " ST", " AVENUE", " AVE", " BOULEVARD", " BLVD", " ROAD", " RD"):
        if street_core.endswith(s):
            street_core = street_core[: -len(s)].strip()
            break
    return num, street_core


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    num, street = _parse(address)
    if not num or not street:
        report = base_report(
            city=SPEC,
            address=address,
            compliance_verdict="invalid_address",
            registrations=[],
            violations={"total": 0, "recent": []},
            sources=[source_url(PORTAL, NOV_ID)],
            extra={"parse_error": "need house number + street, e.g. 2329 Mission St"},
        )
        return report

    where = (
        f"street_number='{escape_soda(num)}' AND "
        f"upper(street_name)='{escape_soda(street)}'"
    )
    rows = await soda_get(PORTAL, NOV_ID, where=where, order="date_filed DESC", limit=40)
    recent = [
        {
            "complaint_number": r.get("complaint_number"),
            "primary_key": r.get("primary_key"),
            "date_filed": r.get("date_filed"),
            "status": r.get("status"),
            "category": r.get("nov_category_description"),
            "item": r.get("item"),
            "street_number": r.get("street_number"),
            "street_name": r.get("street_name"),
            "street_suffix": r.get("street_suffix"),
            "block": r.get("block"),
            "lot": r.get("lot"),
            "receiving_division": r.get("receiving_division"),
        }
        for r in rows[:20]
    ]
    active = [v for v in recent if "not active" not in (v.get("status") or "").lower()]
    if active:
        verdict = "nov_active"
    elif recent:
        verdict = "nov_historical_only"
    else:
        verdict = "no_nov_found"

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=[],
        violations={"total": len(rows), "recent": recent, "active_count": len(active)},
        sources=[source_url(PORTAL, NOV_ID)],
        extra={"product_scope": "dbi_notices_of_violation", "parsed": {"number": num, "street": street}},
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "sf",
        "city_name": "San Francisco",
        "state": "CA",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "nov_historical_only",
        "registered": False,
        "registrations": [],
        "violation_cases": {
            "total": 1,
            "active_count": 0,
            "recent": [{"complaint_number": "201551021", "status": "not active", "category": "sanitation section"}],
        },
    }
