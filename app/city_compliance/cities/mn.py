"""Minneapolis, MN — network facade over the existing ArcGIS join.

Does **not** replace ``/mn/property-check`` or rewrite ``app.mn_compliance``.
Exposes the same live City of Minneapolis open-data product under the US
network path ``/us/mn/property-check`` so Minnesota is part of the multi-city
catalog with a uniform response envelope.
"""

from __future__ import annotations

from typing import Any

from app.city_compliance.models import CitySpec

SPEC = CitySpec(
    code="mn",
    name="Minneapolis",
    state="MN",
    service_name="MN Rental License Check",
    tags=("minneapolis", "rental-license", "compliance", "housing", "diligence"),
    description=(
        "Minneapolis rental license check: is this property licensed? Property "
        "due diligence agent path for Minneapolis Minnesota (Hennepin) housing "
        "compliance open data. GET ?address= → rental license status/tier/units/"
        "expiration, violation history, condemned/boarded, compliance_verdict. "
        "Tenant screening, landlord DD, lending. Live City JSON. US network alias "
        "of /mn/property-check."
    ),
    sample_address="1700 Penn Ave N",
    sample_note=(
        "Free fixed-address sample of the live Minneapolis ArcGIS join "
        "(3 city datasets). Same data as /mn/property-check/sample, wrapped "
        "for the US city network. Any other Minneapolis address requires payment."
    ),
    sources_label="City of Minneapolis Open Data — rental licenses, violations, condemned/boarded",
)


async def check_property(address: str) -> dict[str, Any]:
    """Delegate join to mn_compliance; normalize into network envelope."""
    from app import mn_compliance

    raw = await mn_compliance.check_property(address)
    licenses = raw.get("rental_licenses") or []
    viol = raw.get("violation_cases") or {}
    condemned = raw.get("condemned_or_boarded") or {}

    # Map MN registrations into network `registrations` field.
    registrations = [
        {
            "address": lic.get("address"),
            "apn": lic.get("apn"),
            "license_number": lic.get("license_number"),
            "status": lic.get("status"),
            "tier": lic.get("tier"),
            "category": lic.get("category"),
            "licensed_units": lic.get("licensed_units"),
            "owner_name": lic.get("owner_name"),
            "issue_date": lic.get("issue_date"),
            "expiration_date": lic.get("expiration_date"),
            "ward": lic.get("ward"),
            "neighborhood": lic.get("neighborhood"),
            "community": lic.get("community"),
            "short_term_rental": lic.get("short_term_rental"),
        }
        for lic in licenses
    ]

    return {
        "city": SPEC.code,
        "city_name": SPEC.name,
        "state": SPEC.state,
        "address_queried": raw.get("address_queried") or address.strip(),
        "compliance_verdict": raw.get("compliance_verdict"),
        "registrations": registrations,
        "registered": bool(raw.get("licensed")),
        "violation_cases": viol,
        "condemned_or_boarded": condemned,
        "sources": raw.get("sources") or [],
        "disclaimer": raw.get("disclaimer"),
        "generated_at": raw.get("generated_at"),
        "network_product": "us-city-open-data-compliance",
        "canonical_resource": "/mn/property-check",
        "licensed": raw.get("licensed"),
        "rental_licenses": licenses,  # preserve MN-native keys for agents
    }


def discovery_output_example() -> dict[str, Any]:
    from app import mn_compliance

    ex = dict(mn_compliance.DISCOVERY_OUTPUT_EXAMPLE)
    return {
        "city": "mn",
        "city_name": "Minneapolis",
        "state": "MN",
        "address_queried": SPEC.sample_address,
        "compliance_verdict": ex.get("compliance_verdict", "licensed_with_violations"),
        "registered": True,
        "registrations": ex.get("rental_licenses") or [],
        "violation_cases": ex.get("violation_cases") or {"total": 0, "recent": []},
        "condemned_or_boarded": ex.get("condemned_or_boarded")
        or {"flagged": False, "records": []},
        "canonical_resource": "/mn/property-check",
        "network_product": "us-city-open-data-compliance",
    }
