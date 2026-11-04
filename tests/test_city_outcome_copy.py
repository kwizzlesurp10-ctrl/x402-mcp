"""Outcome-first discovery copy for city property-check products."""

from __future__ import annotations

from app.city_compliance import outcome_copy, registry


def test_all_city_bazaar_descriptions_under_500_chars() -> None:
    from app.city_compliance.coverage import MODE_VIOLATIONS_ONLY, product_mode_for_city

    for mod in registry.CITIES.values():
        spec = mod.SPEC
        desc = outcome_copy.for_spec(spec)
        assert len(desc) <= 500, (spec.code, len(desc))
        assert "verdict" in desc.lower()
        if product_mode_for_city(spec.code, None) == MODE_VIOLATIONS_ONLY:
            assert "does not determine" in desc.lower() or "not rental" in desc.lower()


def test_mcp_blurbs_mention_verdict() -> None:
    assert "verdict" in outcome_copy.mcp_city_check_blurb()
    assert "verdict" in outcome_copy.mcp_city_sample_blurb()
