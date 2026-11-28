"""Canonical schema enforcement for all US city property-check reports."""

from __future__ import annotations

import pytest

from app.city_compliance import publish, registry, schema
from app.city_compliance.schema import CANONICAL_REPORT_KEYS, REGISTRATION_KEYS


def _adapter_shaped_report(code: str) -> dict:
    mod = registry.get_city(code)
    spec = mod.SPEC
    return {
        "city": spec.code,
        "city_name": spec.name,
        "state": spec.state,
        "address_queried": spec.sample_address,
        "compliance_verdict": mod.discovery_output_example().get(
            "compliance_verdict", "unknown"
        ),
        "registrations": mod.discovery_output_example().get("registrations") or [],
        "registered": mod.discovery_output_example().get("registered"),
        "violation_cases": mod.discovery_output_example().get("violation_cases")
        or {"total": 0, "recent": []},
        "sources": [f"https://example.test/{code}"],
        "generated_at": "2026-11-04T00:00:00+00:00",
        "network_product": "us-city-open-data-compliance",
    }


@pytest.mark.parametrize("code", list(registry.known_codes()))
def test_every_city_report_has_canonical_keys(code: str) -> None:
    mod = registry.get_city(code)
    raw = _adapter_shaped_report(code)
    out = publish.prepare_city_report(
        raw, spec=mod.SPEC, address_fallback=mod.SPEC.sample_address
    )
    for key in CANONICAL_REPORT_KEYS:
        assert key in out, f"{code} missing {key}"
    assert out["address_normalized"] == schema.normalize_address_for_match(
        mod.SPEC.sample_address
    )
    assert isinstance(out["registrations"], list)
    assert isinstance(out["violation_cases"], dict)
    for vk in ("total", "open", "abated", "recent", "note"):
        assert vk in out["violation_cases"]


@pytest.mark.parametrize("code", list(registry.known_codes()))
def test_registration_rows_normalized_with_nulls(code: str) -> None:
    mod = registry.get_city(code)
    raw = _adapter_shaped_report(code)
    raw["registrations"] = [
        {
            "address": mod.SPEC.sample_address,
            "license_number": "LIC-1",
            "status": "Active",
        }
    ]
    out = publish.prepare_city_report(
        raw, spec=mod.SPEC, address_fallback=mod.SPEC.sample_address
    )
    row = out["registrations"][0]
    for key in REGISTRATION_KEYS:
        assert key in row


@pytest.mark.parametrize("code", list(registry.public_codes()))
def test_discovery_example_matches_canonical_shape(code: str) -> None:
    mod = registry.get_city(code)
    example = publish.discovery_output_example(mod)
    for key in CANONICAL_REPORT_KEYS:
        assert key in example, f"{code} discovery example missing {key}"
    assert example.get("verdict")
    assert example.get("product_mode")
    assert example.get("coverage_note")


def test_json_schema_document_lists_required_keys() -> None:
    doc = schema.json_schema_document()
    assert "verdict" in doc["properties"]
    assert set(doc["required"]) == set(CANONICAL_REPORT_KEYS)
