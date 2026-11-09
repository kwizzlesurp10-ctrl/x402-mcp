"""JSON Schema fragments for Bazaar discovery (x402.extensions.bazaar).

Examples alone leave ``schema.properties.*.properties`` empty; indexers treat
those routes as non-invocable. Pair every ``discovery_input_example`` with the
matching schema here.
"""

from __future__ import annotations

from typing import Any

ADDRESS_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "address": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120,
            "description": "Street address in the target city (URL-encoded query param).",
        },
    },
    "required": ["address"],
    "additionalProperties": False,
}

CITY_AGENT_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "city_code": {
            "type": "string",
            "minLength": 1,
            "maxLength": 16,
            "description": "City code from /us/cities (e.g. mn, sea, nyc).",
        },
        "address": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120,
            "description": "Street address in that city.",
        },
    },
    "required": ["city_code", "address"],
    "additionalProperties": False,
}

TX_DECISION_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "gas": {
            "type": "string",
            "description": "Gas profile: eth|usdc|erc20|x402 or integer gas units.",
        },
        "urgency": {
            "type": "string",
            "enum": ["now", "soon", "flexible"],
            "description": "How soon the transaction must land.",
        },
    },
    "additionalProperties": True,
}

FINALITY_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tx": {
            "type": "string",
            "pattern": "^0x[0-9a-fA-F]{64}$",
            "description": "Base mainnet transaction hash.",
        },
    },
    "required": ["tx"],
    "additionalProperties": False,
}

DILIGENCE_PACK_BODY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "properties": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "city_code": {"type": "string", "minLength": 1, "maxLength": 16},
                    "address": {"type": "string", "minLength": 1, "maxLength": 120},
                },
                "required": ["city_code", "address"],
                "additionalProperties": False,
            },
        },
        "include_base_pulse_context": {"type": "boolean"},
    },
    "required": ["properties"],
    "additionalProperties": False,
}

POLICY_CHECK_BODY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "payment_required_header": {
            "type": "string",
            "minLength": 1,
            "description": "Inspected merchant PAYMENT-REQUIRED header (base64 wire).",
        },
        "policy": {"type": "object"},
        "request_digest": {"type": "object"},
        "idempotency_key": {"type": "string", "maxLength": 128},
    },
    "required": ["payment_required_header", "policy"],
    "additionalProperties": False,
}


def schema_from_example(value: Any) -> dict[str, Any]:
    """JSON Schema inferred from a discovery output example (OpenAPI-aligned)."""
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if value is None:
        return {}
    if isinstance(value, list):
        items = schema_from_example(value[0]) if value else {}
        return {"type": "array", "items": items}
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {k: schema_from_example(v) for k, v in value.items()},
        }
    return {}


def bazaar_output_schema_has_properties(bazaar: dict[str, Any]) -> bool:
    out = (
        (bazaar.get("schema") or {})
        .get("properties", {})
        .get("output", {})
        .get("properties", {})
        .get("example", {})
        .get("properties", {})
    )
    return bool(out)


def bazaar_input_schema_has_properties(bazaar: dict[str, Any]) -> bool:
    """True when the extension JSON Schema describes non-empty query or body params."""
    inp = (
        (bazaar.get("schema") or {})
        .get("properties", {})
        .get("input", {})
        .get("properties", {})
    )
    for key in ("queryParams", "body"):
        section = inp.get(key) or {}
        props = section.get("properties") if isinstance(section, dict) else None
        if isinstance(props, dict) and props:
            return True
    return False
