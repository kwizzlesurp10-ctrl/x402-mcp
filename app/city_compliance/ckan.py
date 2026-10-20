"""CKAN datastore_search client (Boston and similar portals)."""

from __future__ import annotations

from typing import Any

import httpx

_DEFAULT_TIMEOUT = 25.0


async def datastore_search(
    portal: str,
    resource_id: str,
    *,
    filters: dict[str, Any] | None = None,
    q: str | None = None,
    limit: int = 40,
    offset: int = 0,
    timeout: float = _DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """GET ``{portal}/api/3/action/datastore_search``."""
    url = f"{portal.rstrip('/')}/api/3/action/datastore_search"
    params: dict[str, Any] = {
        "resource_id": resource_id,
        "limit": limit,
        "offset": offset,
    }
    if filters:
        import json

        params["filters"] = json.dumps(filters)
    if q:
        params["q"] = q

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise ValueError(f"CKAN error: {payload}")
        records = payload.get("result", {}).get("records") or []
        if not isinstance(records, list):
            raise ValueError("Unexpected CKAN records payload")
        return records


def resource_page(portal: str, dataset_slug: str) -> str:
    return f"{portal.rstrip('/')}/dataset/{dataset_slug}"
