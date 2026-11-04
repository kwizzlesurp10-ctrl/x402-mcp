"""Single exit path for city property-check JSON returned to buyers."""

from __future__ import annotations

from typing import Any

from app.city_compliance.decision import enrich_decision
from app.city_compliance.models import CitySpec


def prepare_city_report(
    report: dict[str, Any],
    *,
    spec: CitySpec | None = None,
    address_fallback: str = "",
) -> dict[str, Any]:
    """Apply decision-ready fields before HTTP/MCP delivery."""
    city_name = spec.name if spec else report.get("city_name")
    return enrich_decision(
        report,
        city_name=str(city_name) if city_name else None,
        address_fallback=address_fallback,
    )
