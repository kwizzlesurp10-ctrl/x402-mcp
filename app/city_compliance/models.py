"""Shared shapes for city compliance adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Sequence


CheckFn = Callable[[str], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class CitySpec:
    """One sellable city product in the US network (excludes Minneapolis)."""

    code: str  # URL slug, lowercase short code e.g. "sea"
    name: str  # human city name
    state: str  # USPS 2-letter
    service_name: str  # Bazaar serviceName (<=32)
    tags: tuple[str, ...]  # Bazaar tags (<=5, each <=32)
    description: str  # buyer-facing 402 description (<=500 CDP)
    sample_address: str
    sample_note: str
    sources_label: str  # short attribution for free catalog
    price_setting: str = "city_network_price"  # settings attr name
    product_id_prefix: str = "us-city"  # demand + ledger key prefix
    public: bool = True  # False → mounted (402) but omitted from catalogs


def base_report(
    *,
    city: CitySpec,
    address: str,
    compliance_verdict: str,
    registrations: Sequence[dict[str, Any]],
    violations: dict[str, Any],
    sources: Sequence[str],
    extra: dict[str, Any] | None = None,
    disclaimer: str | None = None,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    report: dict[str, Any] = {
        "city": city.code,
        "city_name": city.name,
        "state": city.state,
        "address_queried": address.strip(),
        "compliance_verdict": compliance_verdict,
        "registrations": list(registrations),
        "registered": bool(registrations),
        "violation_cases": violations,
        "sources": list(sources),
        "disclaimer": disclaimer
        or (
            f"Public records from {city.name} open data, served as-is; "
            "not legal advice. Verify with the city before acting."
        ),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "network_product": "us-city-open-data-compliance",
    }
    if extra:
        report.update(extra)
    return report
