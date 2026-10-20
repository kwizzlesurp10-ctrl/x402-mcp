"""US City Open-Data Compliance Network.

Paid x402 property-compliance endpoints for US cities *other than* Minneapolis
(MN stays on ``app.mn_compliance`` / ``/mn/property-check``).

Each city joins public open-data sources into one agent-readable report.
Routes live under ``/us/{city}/property-check`` (+ free ``/sample``).
"""

from app.city_compliance.registry import (
    CITIES,
    get_city,
    list_cities,
    public_codes,
)

__all__ = ["CITIES", "get_city", "list_cities", "public_codes"]
