"""Carto SQL API client (Philadelphia open data and similar)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

_DEFAULT_TIMEOUT = 25.0


async def sql_query(
    carto_base: str,
    sql: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """GET ``{carto_base}/api/v2/sql?q=...`` and return rows."""
    url = f"{carto_base.rstrip('/')}/api/v2/sql"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params={"q": sql})
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise ValueError(f"Carto error: {payload['error']}")
        rows = payload.get("rows") or []
        if not isinstance(rows, list):
            raise ValueError("Unexpected Carto rows payload")
        return rows


def escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")
