"""Coverage-aware verdict rules — no false not_licensed on violations-only feeds."""

from __future__ import annotations

import pytest

from app.city_compliance import coverage, decision, publish, registry
from app.city_compliance.coverage import (
    MODE_LICENSE,
    MODE_LICENSE_AND_VIOLATIONS,
    MODE_NONE,
    MODE_VIOLATIONS_ONLY,
)
from app.city_compliance.decision import (
    VERDICT_LICENSED,
    VERDICT_NO_VIOLATIONS_FOUND,
    VERDICT_NOT_LICENSED,
    VERDICT_UNKNOWN,
    VERDICT_VIOLATIONS_OPEN,
)


def _report(code: str, compliance: str, **extra: object) -> dict:
    mod = registry.get_city(code)
    base: dict = {
        "city": code,
        "city_name": mod.SPEC.name,
        "state": mod.SPEC.state,
        "address_queried": mod.SPEC.sample_address,
        "compliance_verdict": compliance,
        "registrations": [],
        "registered": False,
        "violation_cases": {"total": 0, "recent": []},
        "sources": ["https://example.test/feed"],
        "generated_at": "2026-11-04T00:00:00+00:00",
    }
    base.update(extra)
    return base


VIOLATIONS_ONLY_CITIES = ("chi", "bos", "phi", "kc", "lax", "gain", "sf")


@pytest.mark.parametrize("code", VIOLATIONS_ONLY_CITIES)
def test_violations_only_never_not_licensed(code: str) -> None:
    assert coverage.product_mode_for_city(code, None) == MODE_VIOLATIONS_ONLY
    for compliance in (
        "no_violations_found",
        "violations_closed_only",
        "nov_historical_only",
        "no_open_violations",
    ):
        out = publish.prepare_city_report(
            _report(code, compliance),
            spec=registry.get_city(code).SPEC,
            address_fallback="1 Main St",
        )
        assert out["verdict"] != VERDICT_NOT_LICENSED, (code, compliance)
        assert out["product_mode"] == MODE_VIOLATIONS_ONLY
        assert "does not include rental" in out["coverage_note"].lower()


@pytest.mark.parametrize("code", VIOLATIONS_ONLY_CITIES)
def test_violations_only_open_cases(code: str) -> None:
    out = publish.prepare_city_report(
        _report(
            code,
            "violations_open",
            violation_cases={"total": 2, "open": 1, "recent": []},
        ),
        spec=registry.get_city(code).SPEC,
        address_fallback="1 Main St",
    )
    assert out["verdict"] == VERDICT_VIOLATIONS_OPEN


@pytest.mark.parametrize("code", ("atl", "mia"))
def test_placeholder_cities_unknown_verdict(code: str) -> None:
    assert coverage.product_mode_for_city(code, None) == MODE_NONE
    out = publish.prepare_city_report(
        _report(code, "str_unlicensed", sources=[]),
        spec=registry.get_city(code).SPEC,
        address_fallback="1 Main St",
    )
    assert out["verdict"] == VERDICT_UNKNOWN
    assert out["confidence"] == "low"
    assert out["product_mode"] == MODE_NONE


def test_license_cities_still_allow_not_licensed() -> None:
    out = publish.prepare_city_report(
        _report("sea", "unregistered"),
        spec=registry.get_city("sea").SPEC,
        address_fallback="1 Main St",
    )
    assert out["product_mode"] == MODE_LICENSE
    assert out["verdict"] == VERDICT_NOT_LICENSED


def test_mn_unlicensed_is_not_licensed() -> None:
    out = publish.prepare_city_report(
        _report("mn", "unlicensed"),
        spec=registry.get_city("mn").SPEC,
        address_fallback="1 Main St",
    )
    assert out["product_mode"] == MODE_LICENSE_AND_VIOLATIONS
    assert out["verdict"] == VERDICT_NOT_LICENSED


def test_nyc_unregistered_with_license_feed() -> None:
    out = publish.prepare_city_report(
        _report("nyc", "unregistered"),
        spec=registry.get_city("nyc").SPEC,
        address_fallback="1 Main St",
    )
    assert out["product_mode"] == MODE_LICENSE_AND_VIOLATIONS
    assert out["verdict"] == VERDICT_NOT_LICENSED


@pytest.mark.parametrize(
    ("code", "mode"),
    [
        ("mn", MODE_LICENSE_AND_VIOLATIONS),
        ("moco", MODE_LICENSE_AND_VIOLATIONS),
        ("nyc", MODE_LICENSE_AND_VIOLATIONS),
        ("sea", MODE_LICENSE),
        ("den", MODE_LICENSE),
        ("chi", MODE_VIOLATIONS_ONLY),
        ("sf", MODE_VIOLATIONS_ONLY),
        ("atl", MODE_NONE),
        ("mia", MODE_NONE),
    ],
)
def test_product_mode_registry(code: str, mode: str) -> None:
    assert coverage.product_mode_for_city(code, None) == mode


@pytest.mark.parametrize("code", list(registry.public_codes()))
def test_public_city_prepare_has_product_mode(code: str) -> None:
    mod = registry.get_city(code)
    ex = mod.discovery_output_example()
    out = publish.prepare_city_report(
        {**ex, "city": code, "generated_at": "2026-11-04T00:00:00+00:00"},
        spec=mod.SPEC,
        address_fallback=mod.SPEC.sample_address,
    )
    assert out["product_mode"] in (
        MODE_LICENSE,
        MODE_LICENSE_AND_VIOLATIONS,
        MODE_VIOLATIONS_ONLY,
    )
    assert out["coverage_note"]
    if out["product_mode"] == MODE_VIOLATIONS_ONLY:
        assert out["verdict"] in (
            VERDICT_VIOLATIONS_OPEN,
            VERDICT_NO_VIOLATIONS_FOUND,
            VERDICT_UNKNOWN,
        )
