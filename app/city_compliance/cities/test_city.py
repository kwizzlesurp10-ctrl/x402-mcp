"""Sandbox test city — deterministic test fixture for testing and agent evaluation."""

from __future__ import annotations

import time
from typing import Any

from app.city_compliance.models import CitySpec, base_report

SPEC = CitySpec(
    code="test",
    name="Test Sandbox City",
    state="TS",
    service_name="Test Compliance Sandbox",
    tags=("test", "sandbox", "fixture", "compliance"),
    description=(
        "Deterministic synthetic property compliance fixture for integration testing, "
        "smoke testing, and agent verification without hitting external city open-data portals."
    ),
    sample_address="123 Test St",
    sample_note=(
        "Free deterministic test fixture for test runners, CI, and agent evaluation. "
        "Returns a mock licensed property compliance report."
    ),
    sources_label="Synthetic Open Data Test Sandbox",
    public=False,
)

_CACHE_TTL = 900
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def check_property(address: str) -> dict[str, Any]:
    key = address.strip().upper()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] <= _CACHE_TTL:
        return hit[1]

    report = base_report(
        city=SPEC,
        address=address,
        compliance_verdict="licensed_clean",
        registrations=[
            {
                "address": address.strip(),
                "apn": "000-000-000",
                "license_number": "TEST-LIC-12345",
                "status": "Active",
                "tier": "Tier 1",
                "category": "Rental Dwelling",
                "licensed_units": 1,
                "owner_name": "Sandbox Test Owner",
                "issue_date": "2026-01-01",
                "expiration_date": "2027-01-01",
            }
        ],
        violations={"total": 0, "recent": []},
        sources=["https://sandbox.test/compliance-data"],
        extra={"product_scope": "rental_license_sandbox", "active_licenses": 1},
        disclaimer="Synthetic test sandbox data for integration testing; not a real municipality.",
    )

    _cache[key] = (time.monotonic(), report)
    return report


def discovery_output_example() -> dict[str, Any]:
    return {
        "city": "test",
        "city_name": "Test Sandbox City",
        "state": "TS",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": "licensed_clean",
        "registered": True,
        "registrations": [
            {
                "address": SPEC.sample_address,
                "apn": "000-000-000",
                "license_number": "TEST-LIC-12345",
                "status": "Active",
            }
        ],
        "violation_cases": {"total": 0, "recent": []},
        "sources": ["https://sandbox.test/compliance-data"],
        "generated_at": "2026-11-28T00:00:00+00:00",
        "network_product": "us-city-open-data-compliance",
    }
