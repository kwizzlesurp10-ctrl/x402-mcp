"""Regression: each A2A city skill must serve ITS OWN payment challenge.

Before the fix, the ``build_payment_header`` lambda in ``_skill_bindings()``
late-bound ``spec``/``input_example``/``output_example`` from the loop, so all
17 city skills returned San Diego's challenge URL. A buyer following the A2A
challenge would pay for (and settle against) the wrong city.

No network, no payment, no settle — the challenge header is built locally.
"""
from __future__ import annotations

import base64
import json

from app.a2a_rpc import _skill_bindings


def _challenge_for(skill_id: str) -> dict:
    binding = _skill_bindings()[skill_id]
    return json.loads(base64.b64decode(binding.build_payment_header()))


def test_city_skills_serve_their_own_resource_url():
    """Each property-check-<code> skill points at /us/<code>/property-check."""
    bindings = _skill_bindings()
    city_skills = sorted(k for k in bindings if k.startswith("property-check-"))
    assert city_skills, "expected A2A city skills to be registered"

    wrong = {}
    for skill_id in city_skills:
        code = skill_id.removeprefix("property-check-")
        resource = _challenge_for(skill_id)["resource"]
        url = resource.get("url", "")
        if f"/us/{code}/property-check" not in url:
            wrong[skill_id] = url

    assert not wrong, f"city skills served the wrong challenge: {wrong}"


def test_city_skills_serve_their_own_service_name():
    """The challenge's serviceName must not be another city's name."""
    from app.city_compliance import registry

    expected = {entry["code"]: entry["service_name"] for entry in registry.list_cities()}
    wrong = {}
    for code, service_name in expected.items():
        skill_id = f"property-check-{code}"
        if skill_id not in _skill_bindings():
            continue
        got = _challenge_for(skill_id)["resource"].get("serviceName")
        if got != service_name:
            wrong[skill_id] = {"expected": service_name, "got": got}

    assert not wrong, f"city skills advertised the wrong serviceName: {wrong}"


def test_city_skill_input_example_matches_its_city():
    """The challenge's input example must be that city's own sample address."""
    from app.city_compliance import registry

    wrong = {}
    for code in registry.public_codes():
        skill_id = f"property-check-{code}"
        if skill_id not in _skill_bindings():
            continue
        challenge = _challenge_for(skill_id)
        example = (challenge.get("extensions", {}) or {}).get("bazaar", {}) or {}
        input_info = example.get("info", {}) or {}
        params = (input_info.get("input", {}) or {}).get("queryParams", {}) or {}
        sample = registry.get_city(code).SPEC.sample_address
        if params.get("address") != sample:
            wrong[skill_id] = {"expected": sample, "got": params.get("address")}

    assert not wrong, f"city skills advertised the wrong sample address: {wrong}"
