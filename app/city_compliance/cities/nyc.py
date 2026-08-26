"""New York City, NY — HPD multiple-dwelling registration + HMC violations."""

from __future__ import annotations

import re
import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report
from app.city_compliance.socrata import escape_soda, soda_get, source_url

PORTAL = "https://data.cityofnewyork.us"
REG_ID = "tesw-yqqr"  # Multiple Dwelling Registrations
VIOL_ID = "wvxf-dwi5"  # Housing Maintenance Code Violations

SPEC = CitySpec(
    code="nyc",
    name="New York City",
    state="NY",
    service_name="NYC HPD Violations Address",
    tags=("nyc", "hpd", "violations", "housing", "diligence"),
    description=(
        "NYC HPD violations address check: is this property licensed / HPD-"
        "registered, and are there open Housing Maintenance Code violations? "
        "Property due diligence agent for New York City multi-dwelling housing "
        "compliance open data. GET ?address= (house + street, optional borough) "
        "→ registration window, BIN/block/lot, recent HMC violations JSON. "
        "Tenant screening, landlord DD."
    ),
    sample_address="787 EAST 56 STREET BROOKLYN",
    sample_note=(
        "Free fixed-address sample of NYC HPD registration + HMC violation join. "
        "Any other NYC address requires payment."
    ),
    sources_label="NYC Open Data — HPD Multiple Dwelling Registrations + HMC Violations",
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

_BORO_HINTS = {
    "MANHATTAN": "MANHATTAN",
    "NY": "MANHATTAN",
    "NEW YORK": "MANHATTAN",
    "BROOKLYN": "BROOKLYN",
    "BK": "BROOKLYN",
    "QUEENS": "QUEENS",
    "QN": "QUEENS",
    "BRONX": "BRONX",
    "BX": "BRONX",
    "STATEN ISLAND": "STATEN ISLAND",
    "SI": "STATEN ISLAND",
}


def _parse_address(address: str) -> tuple[str, str, str | None]:
    """Return (house_number, street_name, boro_or_none)."""
    raw = re.sub(r"\s+", " ", address.strip().upper())
    boro: str | None = None
    for hint, canon in sorted(_BORO_HINTS.items(), key=lambda x: -len(x[0])):
        if raw.endswith(" " + hint) or raw.endswith("," + hint) or raw.endswith(", " + hint):
            boro = canon
            raw = raw[: -len(hint)].rstrip(" ,")
            break
        if raw.startswith(hint + " "):
            boro = canon
            raw = raw[len(hint) :].strip(" ,")
            break
    m = re.match(r"^(\d+[A-Z\-]*(?:\s+FRONT)?)\s+(.+)$", raw)
    if not m:
        # Fallback: whole string as street search seed
        return "", raw, boro
    return m.group(1).strip(), m.group(2).strip(), boro


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    house, street, boro = _parse_address(address)
    if not street:
        report = base_report(
            city=SPEC,
            address=address,
            compliance_verdict="invalid_address",
            registrations=[],
            violations={"total": 0, "recent": []},
            sources=[source_url(PORTAL, REG_ID), source_url(PORTAL, VIOL_ID)],
            extra={"parse_error": "need house number and street, e.g. 787 EAST 56 STREET BROOKLYN"},
        )
        return report

    where_parts = [f"upper(streetname)='{escape_soda(street)}'"]
    if house:
        where_parts.append(f"housenumber='{escape_soda(house.split()[0])}'")
    if boro:
        where_parts.append(f"upper(boro)='{escape_soda(boro)}'")
    where = " AND ".join(where_parts)

    regs = await soda_get(PORTAL, REG_ID, where=where, limit=20)
    # Broader street+house if exact miss and we had boro
    if not regs and boro and house:
        where2 = (
            f"upper(streetname)='{escape_soda(street)}' AND "
            f"housenumber='{escape_soda(house.split()[0])}'"
        )
        regs = await soda_get(PORTAL, REG_ID, where=where2, limit=20)

    building_ids = sorted({str(r["buildingid"]) for r in regs if r.get("buildingid")})
    viol_rows: list[dict[str, Any]] = []
    if building_ids:
        # SODA IN list
        ids = ", ".join(f"'{escape_soda(b)}'" for b in building_ids[:10])
        viol_rows = await soda_get(
            PORTAL,
            VIOL_ID,
            where=f"buildingid in ({ids})",
            order="inspectiondate DESC",
            limit=50,
        )
    else:
        # Address-only violation probe when unregistered
        vwhere = f"upper(streetname)='{escape_soda(street)}'"
        if house:
            vwhere += f" AND housenumber like '{escape_soda(house.split()[0])}%'"
        if boro:
            vwhere += f" AND upper(boro)='{escape_soda(boro)}'"
        viol_rows = await soda_get(
            PORTAL, VIOL_ID, where=vwhere, order="inspectiondate DESC", limit=25
        )

    registrations = [
        {
            "registration_id": r.get("registrationid"),
            "building_id": r.get("buildingid"),
            "borough": r.get("boro"),
            "house_number": r.get("housenumber"),
            "street": r.get("streetname"),
            "zip": r.get("zip"),
            "bin": r.get("bin"),
            "block": r.get("block"),
            "lot": r.get("lot"),
            "last_registration_date": r.get("lastregistrationdate"),
            "registration_end_date": r.get("registrationenddate"),
        }
        for r in regs
    ]
    recent = [
        {
            "violation_id": v.get("violationid"),
            "class": v.get("class"),
            "inspection_date": v.get("inspectiondate"),
            "apartment": v.get("apartment"),
            "status": v.get("currentstatus") or v.get("violationstatus"),
            "description": v.get("novdescription") or v.get("description"),
            "borough": v.get("boro"),
            "house_number": v.get("housenumber"),
            "street": v.get("streetname"),
        }
        for v in viol_rows[:15]
    ]
    openish = [
        v
        for v in recent
        if (v.get("status") or "").upper() not in {"CLOSE", "CLOSED", "DISMISSED"}
    ]

    if registrations and openish:
        verdict = "registered_with_violations"
    elif registrations:
        verdict = "registered_clean"
    elif viol_rows:
        verdict = "unregistered_with_violations"
    else:
        verdict = "unregistered"

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=registrations,
        violations={"total": len(viol_rows), "recent": recent, "openish_count": len(openish)},
        sources=[source_url(PORTAL, REG_ID), source_url(PORTAL, VIOL_ID)],
        extra={"parsed": {"house_number": house, "street": street, "borough": boro}},
    )
    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "nyc",
        "city_name": "New York City",
        "state": "NY",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "registered_clean",
        "registered": True,
        "registrations": [
            {
                "registration_id": "825850",
                "borough": "BROOKLYN",
                "house_number": "787",
                "street": "EAST 56 STREET",
                "registration_end_date": "2026-09-01T00:00:00.000",
            }
        ],
        "violation_cases": {"total": 0, "recent": []},
    }
