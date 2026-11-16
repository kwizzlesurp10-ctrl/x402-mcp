"""Graceful degradation when city open-data feeds are unavailable."""

from __future__ import annotations

from app.city_compliance.models import CitySpec, base_report


def upstream_unavailable_report(spec: CitySpec, address: str) -> dict:
    """Report buyers can use when upstream fails (sample / preview paths)."""
    note = (
        "City open-data source was unavailable when this report was generated; "
        "verdict is unknown — not evidence that the address is unlicensed or illegal to rent."
    )
    return base_report(
        city=spec,
        address=address,
        compliance_verdict="unknown",
        registrations=[],
        violations={"total": 0, "recent": [], "note": note},
        sources=[],
        extra={"upstream_status": "unavailable", "product_scope": "upstream_degraded"},
    )