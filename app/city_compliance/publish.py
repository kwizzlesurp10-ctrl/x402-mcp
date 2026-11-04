"""Single exit path for city property-check JSON returned to buyers."""

from __future__ import annotations

from typing import Any

from app.city_compliance.decision import enrich_decision
from app.city_compliance.models import CitySpec
from app.city_compliance.schema import apply_canonical_schema


def prepare_city_report(
    report: dict[str, Any],
    *,
    spec: CitySpec | None = None,
    address_fallback: str = "",
) -> dict[str, Any]:
    """Apply decision-ready fields and canonical schema before HTTP/MCP delivery."""
    city_name = spec.name if spec else report.get("city_name")
    enriched = enrich_decision(
        report,
        city_name=str(city_name) if city_name else None,
        address_fallback=address_fallback,
    )
    return apply_canonical_schema(
        enriched,
        city=spec.code if spec else enriched.get("city"),
        city_name=spec.name if spec else enriched.get("city_name"),
        state=spec.state if spec else enriched.get("state"),
    )


def discovery_output_example(mod: Any) -> dict[str, Any]:
    """Bazaar/OpenAPI output example with full canonical shape."""
    raw = mod.discovery_output_example()
    spec: CitySpec = mod.SPEC
    return prepare_city_report(
        raw,
        spec=spec,
        address_fallback=spec.sample_address,
    )
