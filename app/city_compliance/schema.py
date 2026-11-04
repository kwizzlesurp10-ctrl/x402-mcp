"""Canonical JSON shape for US city property-check reports."""

from __future__ import annotations

from typing import Any

from app.city_compliance.decision import normalize_address_for_match

# Top-level keys every city response must include (null when not applicable).
CANONICAL_REPORT_KEYS: tuple[str, ...] = (
    "city",
    "city_name",
    "state",
    "address_queried",
    "address_normalized",
    "verdict",
    "summary",
    "compliance_verdict",
    "product_mode",
    "coverage_note",
    "confidence",
    "data_as_of",
    "source_url",
    "registered",
    "licensed",
    "key_dates",
    "open_violations_count",
    "violation_cases_total",
    "registrations",
    "violation_cases",
    "records",
    "sources",
    "disclaimer",
    "generated_at",
    "network_product",
    "canonical_resource",
)

REGISTRATION_KEYS: tuple[str, ...] = (
    "address",
    "address_normalized",
    "license_number",
    "registration_number",
    "status",
    "issue_date",
    "expiration_date",
    "record_url",
    "parcel_number",
    "license_type",
    "rental_units",
)

VIOLATION_CASE_KEYS: tuple[str, ...] = (
    "total",
    "open",
    "abated",
    "recent",
    "note",
)


def normalize_registration(row: dict[str, Any]) -> dict[str, Any]:
    lic = row.get("license_number") or row.get("permitnum")
    reg = row.get("registration_number") or row.get("permitnum") or lic
    addr = row.get("address") or row.get("originaladdress1")
    out: dict[str, Any] = {
        "address": addr,
        "address_normalized": normalize_address_for_match(str(addr or "")) or None,
        "license_number": lic,
        "registration_number": reg,
        "status": row.get("status") or row.get("statuscurrent"),
        "issue_date": row.get("issue_date")
        or row.get("registered_date")
        or row.get("license_issue_date"),
        "expiration_date": row.get("expiration_date")
        or row.get("expiresdate")
        or row.get("expiry_date"),
        "record_url": row.get("record_url")
        or (
            (row.get("link") or {}).get("url")
            if isinstance(row.get("link"), dict)
            else row.get("link")
        ),
        "parcel_number": row.get("parcel_number") or row.get("apn"),
        "license_type": row.get("license_type") or row.get("license_type"),
        "rental_units": row.get("rental_units") or row.get("licensed_units"),
    }
    # Preserve city-specific fields under extra keys at same level for compat
    for key, val in row.items():
        if key not in out and key not in REGISTRATION_KEYS:
            out[key] = val
    return _null_pad(out, REGISTRATION_KEYS)


def normalize_violation_cases(viol: Any) -> dict[str, Any]:
    if not isinstance(viol, dict):
        base: dict[str, Any] = {k: None for k in VIOLATION_CASE_KEYS}
        base["total"] = 0
        base["recent"] = []
        return base
    out: dict[str, Any] = {
        "total": viol.get("total"),
        "open": viol.get("open"),
        "abated": viol.get("abated"),
        "recent": viol.get("recent") if isinstance(viol.get("recent"), list) else [],
        "note": viol.get("note"),
    }
    for key, val in viol.items():
        if key not in out:
            out[key] = val
    return _null_pad(out, VIOLATION_CASE_KEYS)


def _null_pad(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    for key in keys:
        if key not in row:
            row[key] = None
    return row


def apply_canonical_schema(
    report: dict[str, Any],
    *,
    city: str | None = None,
    city_name: str | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    """Ensure uniform keys and normalized nested registration rows."""
    out = dict(report)
    out["city"] = out.get("city") or city
    out["city_name"] = out.get("city_name") or city_name
    out["state"] = out.get("state") or state
    addr = str(out.get("address_queried") or "")
    out["address_normalized"] = normalize_address_for_match(addr) or None

    regs = out.get("registrations")
    if isinstance(regs, list):
        out["registrations"] = [
            normalize_registration(r) if isinstance(r, dict) else r for r in regs
        ]
    else:
        out["registrations"] = []

    out["violation_cases"] = normalize_violation_cases(out.get("violation_cases"))
    total = out["violation_cases"].get("total")
    out["violation_cases_total"] = int(total) if total is not None else 0

    if out.get("licensed") is None and isinstance(out.get("registered"), bool):
        out["licensed"] = out["registered"]
    if out.get("registered") is None and isinstance(out.get("licensed"), bool):
        out["registered"] = out["licensed"]

    if "canonical_resource" not in out:
        out["canonical_resource"] = None

    if "key_dates" not in out or not isinstance(out.get("key_dates"), dict):
        out["key_dates"] = {"issued": None, "expires": None}
    else:
        kd = dict(out["key_dates"])
        kd.setdefault("issued", None)
        kd.setdefault("expires", None)
        out["key_dates"] = kd

    for key in CANONICAL_REPORT_KEYS:
        if key in out:
            continue
        if key in ("registrations", "sources"):
            out[key] = []
        elif key == "violation_cases":
            out[key] = normalize_violation_cases(None)
        elif key == "records":
            out[key] = out.get("records") or {}
        elif key == "key_dates":
            out[key] = {"issued": None, "expires": None}
        else:
            out[key] = None

    return out


def json_schema_document() -> dict[str, Any]:
    """Machine-readable schema for docs and discovery."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "USCityPropertyCheckReport",
        "type": "object",
        "required": list(CANONICAL_REPORT_KEYS),
        "properties": {
            "verdict": {
                "type": "string",
                "enum": [
                    "licensed",
                    "not_licensed",
                    "expired",
                    "violations_open",
                    "no_violations_found",
                    "flagged",
                    "unknown",
                ],
                "description": "Normalized decision token for agent branching.",
            },
            "product_mode": {
                "type": "string",
                "enum": [
                    "license",
                    "license_and_violations",
                    "violations_only",
                    "none",
                ],
                "description": "What this city product can conclude (licensing vs violations-only vs unwired).",
            },
            "coverage_note": {
                "type": "string",
                "description": "Explicit scope warning for agents (e.g. violations-only feeds).",
            },
            "summary": {"type": "string"},
            "compliance_verdict": {
                "type": "string",
                "description": "Legacy city-specific token (stable for existing integrations).",
            },
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "registrations": {
                "type": "array",
                "items": {"type": "object", "properties": {k: {"type": ["string", "integer", "null"]} for k in REGISTRATION_KEYS}},
            },
            "records": {
                "type": "object",
                "description": "Structured copy of raw adapter fields.",
            },
        },
    }
