"""San Diego, CA — short-term rental licenses (City open-data CSV)."""

from __future__ import annotations

import csv
import io
import re
import time
from typing import Any

import httpx

from app.city_compliance import outcome_copy
from app.city_compliance.models import CitySpec, base_report

# maps.sandiego.gov ArcGIS (legacy) stopped resolving; authoritative feed is SANDAG open data.
STRO_CSV_URL = "https://seshat.datasd.org/stro_licenses/stro_licenses_datasd.csv"

SPEC = CitySpec(
    code="sd",
    name="San Diego",
    state="CA",
    service_name="San Diego STR License Check",
    tags=("sandiego", "str", "rental-license", "housing", "diligence"),
    description=outcome_copy.paid_route_description(code="sd", name="San Diego"),
    sample_address="123 MAIN ST",
    sample_note=(
        "Free fixed-address sample of San Diego short-term rental licenses. "
        "Any other San Diego address requires payment."
    ),
    sources_label="City of San Diego Open Data — Active STRO licenses (CSV)",
)

_CACHE_TTL = 900
_query_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_csv_cache: tuple[float, list[dict[str, str]]] | None = None

_STOPWORDS = frozenset({"SAN", "DIEGO", "CA", "CALIFORNIA", "UNIT", "APT", "STE", "#"})


def _address_tokens(address: str) -> list[str]:
    raw = re.sub(r"[^A-Z0-9\s]", " ", address.strip().upper())
    return [t for t in raw.split() if t and t not in _STOPWORDS]


async def _load_license_rows() -> list[dict[str, str]]:
    global _csv_cache
    now = time.monotonic()
    if _csv_cache and now - _csv_cache[0] <= _CACHE_TTL:
        return _csv_cache[1]

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.get(STRO_CSV_URL)
        response.raise_for_status()
        text = response.text

    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(row) for row in reader]
    _csv_cache = (now, rows)
    return rows


def _match_rows(rows: list[dict[str, str]], address: str) -> list[dict[str, str]]:
    tokens = _address_tokens(address)
    if not tokens:
        return []
    matched: list[dict[str, str]] = []
    for row in rows:
        hay = (row.get("address") or "").upper()
        if all(tok in hay for tok in tokens):
            matched.append(row)
        if len(matched) >= 25:
            break
    return matched


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _query_cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    rows = _match_rows(await _load_license_rows(), address)

    registrations = [
        {
            "address": r.get("address"),
            "license_number": r.get("license_id"),
            "license_tier": r.get("tier"),
            "expiration_date": r.get("date_expiration"),
            "status": "Active",
            "zip": r.get("zip"),
            "community_planning_area": r.get("community_planning_area"),
        }
        for r in rows
    ]

    verdict = "str_licensed_active" if registrations else "str_unlicensed"

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict=verdict,
        registrations=registrations,
        violations={
            "total": 0,
            "recent": [],
            "note": "STR license feed only; no code-enforcement join in this product",
        },
        sources=[STRO_CSV_URL],
        extra={"product_scope": "short_term_rental_license", "active_licenses": len(registrations)},
    )
    _query_cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "sd",
        "city_name": "San Diego",
        "state": "CA",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "str_unlicensed",
        "registered": False,
        "registrations": [],
        "violation_cases": {"total": 0, "recent": []},
    }