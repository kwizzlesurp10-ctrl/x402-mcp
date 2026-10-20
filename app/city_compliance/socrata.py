"""Minimal Socrata SODA 2.0 client for city open-data portals."""

from __future__ import annotations

from typing import Any

import httpx

_DEFAULT_TIMEOUT = 25.0


def escape_soda(value: str) -> str:
    """Escape a string for SODA ``$where`` single-quoted literals."""
    return value.replace("'", "''")


async def soda_get(
    base_url: str,
    resource_id: str,
    *,
    where: str | None = None,
    q: str | None = None,
    select: str | None = None,
    order: str | None = None,
    limit: int = 20,
    timeout: float = _DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """GET ``{base}/resource/{id}.json`` with optional SODA params.

    ``base_url`` is the portal origin, e.g. ``https://data.seattle.gov``.
    """
    url = f"{base_url.rstrip('/')}/resource/{resource_id}.json"
    params: dict[str, str | int] = {"$limit": limit}
    if where:
        params["$where"] = where
    if q:
        params["$q"] = q
    if select:
        params["$select"] = select
    if order:
        params["$order"] = order

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(f"Socrata error on {resource_id}: {data}")
        if not isinstance(data, list):
            raise ValueError(f"Unexpected Socrata payload for {resource_id}")
        return data


def address_like_clause(column: str, address: str) -> str:
    """``upper(column) like 'NEEDLE%'`` for street-prefix match."""
    needle = escape_soda(address.strip().upper())
    return f"upper({column}) like '{needle}%'"


def source_url(base_url: str, resource_id: str) -> str:
    return f"{base_url.rstrip('/')}/resource/{resource_id}.json"
