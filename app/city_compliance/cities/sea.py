"""Seattle, WA — Rental Registration & Inspection Ordinance (RRIO)."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import address_like_clause, soda_get, source_url

PORTAL = "https://data.seattle.gov"
RESOURCE = "j2xh-c7vt"  # Rental Property Registration

SPEC = CitySpec(
    code="sea",
    name="Seattle",
    state="WA",
    service_name="Seattle Rental Registration",
    tags=("seattle", "rental", "registration", "housing", "diligence"),
    description=(
        "Seattle rental registration check (RRIO): is this property licensed / "
        "registered? Property due diligence agent for Seattle housing compliance "
        "open data. GET ?address= → rental registration status, unit count, "
        "expiration, contact. Live City of Seattle JSON. Tenant screening, "
        "landlord DD, real-estate checks."
    ),
    sample_address="1531 BELMONT AVE",
    sample_note=(
        "Free fixed-address sample of Seattle RRIO registration join "
        "(City of Seattle open data). Any other Seattle address requires payment."
    ),
    sources_label="City of Seattle Open Data — Rental Property Registration",
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
        where=address_like_clause("originaladdress1", address),
        limit=15,
    )
    registrations = [
        {
            "address": r.get("originaladdress1"),
            "city": r.get("originalcity"),
            "state": r.get("originalstate"),
            "zip": r.get("originalzip"),
            "registration_number": r.get("permitnum"),
            "status": r.get("statuscurrent"),
            "property_name": r.get("propertyname"),
            "rental_units": _num(r.get("rentalhousingunits")),
            "registered_date": r.get("registereddate"),
            "expiration_date": r.get("expiresdate"),
            "contact_name": r.get("propertycontactname"),
            "record_url": (r.get("link") or {}).get("url")
            if isinstance(r.get("link"), dict)
            else r.get("link"),
        }
        for r in rows
    ]
    active = [
        r
        for r in registrations
        if (r.get("status") or "").lower().startswith("active")
    ]
    if active:
        verdict = "registered_active"
    elif registrations:
        verdict = "registered_inactive"
    else:
        verdict = "unregistered"

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=registrations,
        violations={"total": 0, "recent": [], "note": "RRIO dataset has no violation join"},
        sources=[source_url(PORTAL, RESOURCE)],
        extra={"active_registrations": len(active)},
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "sea",
        "city_name": "Seattle",
        "state": "WA",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "registered_active",
        "registered": True,
        "registrations": [
            {
                "address": "1531 BELMONT AVE",
                "registration_number": "001-0100004",
                "status": "Active Registration",
                "rental_units": 23,
                "expiration_date": "2027-04-21",
            }
        ],
        "violation_cases": {"total": 0, "recent": []},
    }


def _num(v: Any) -> int | None:
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None
