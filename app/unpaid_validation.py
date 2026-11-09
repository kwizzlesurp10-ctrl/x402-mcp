"""Validate unpaid request shape before returning a 402 challenge.

Malformed callers should receive 422 with a pointer to OpenAPI — not a
payment quote they cannot usefully fulfill.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi.responses import JSONResponse

_FINALITY_TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def _pointer(fragment: str) -> dict[str, str]:
    return {"openapi": f"/openapi.json{fragment}"}


def validation_response(
    *,
    error: str,
    detail: str,
    openapi_fragment: str,
    status_code: int = 422,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "detail": detail,
            "schema": _pointer(openapi_fragment),
        },
    )


def unpaid_address_invalid(address: str | None) -> JSONResponse | None:
    if address is None or not str(address).strip() or len(str(address)) > 120:
        return validation_response(
            error="validation_error",
            detail="address is required and must be 1-120 characters",
            openapi_fragment="#/paths/~1mn~1property-check/get/parameters",
        )
    return None


def unpaid_city_address_invalid(address: str | None, city_code: str) -> JSONResponse | None:
    frag = f"#/paths/~1us~1{city_code}~1property-check/get/parameters"
    if address is None or not str(address).strip() or len(str(address)) > 120:
        return validation_response(
            error="validation_error",
            detail="address is required and must be 1-120 characters",
            openapi_fragment=frag,
        )
    return None


def unpaid_finality_tx_invalid(tx: str | None) -> JSONResponse | None:
    if tx is None or not str(tx).strip():
        return validation_response(
            error="validation_error",
            detail="tx query parameter is required",
            openapi_fragment="#/paths/~1base~1finality-check/get/parameters",
        )
    if not _FINALITY_TX_RE.match(str(tx).strip()):
        return validation_response(
            error="validation_error",
            detail="tx must be a 0x-prefixed 32-byte Base mainnet transaction hash",
            openapi_fragment="#/paths/~1base~1finality-check/get/parameters",
        )
    return None


def unpaid_agent_query_invalid(city_code: str | None, address: str | None) -> JSONResponse | None:
    code = (city_code or "").strip().lower()
    if not code or len(code) > 16:
        return validation_response(
            error="validation_error",
            detail="city_code is required (see /us/cities)",
            openapi_fragment="#/paths/~1agent~1property-due-diligence/get/parameters",
        )
    if address is None or not str(address).strip() or len(str(address)) > 120:
        return validation_response(
            error="validation_error",
            detail="address is required and must be 1-120 characters",
            openapi_fragment="#/paths/~1agent~1property-due-diligence/get/parameters",
        )
    return None


async def unpaid_diligence_body_invalid(raw: Any) -> JSONResponse | None:
    if not isinstance(raw, dict):
        return validation_response(
            error="validation_error",
            detail="JSON body must be an object with properties array",
            openapi_fragment="#/paths/~1tasks~1us-rental-diligence/post/requestBody",
        )
    props = raw.get("properties")
    if not isinstance(props, list) or len(props) < 1:
        return validation_response(
            error="validation_error",
            detail="properties must be a non-empty array of {city_code, address}",
            openapi_fragment="#/paths/~1tasks~1us-rental-diligence/post/requestBody",
        )
    return None
