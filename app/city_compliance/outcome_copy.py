"""Outcome-first discovery copy for US city property-check products."""

from __future__ import annotations

from app.city_compliance.coverage import (
    MODE_LICENSE,
    MODE_LICENSE_AND_VIOLATIONS,
    MODE_NONE,
    MODE_VIOLATIONS_ONLY,
    product_mode_for_city,
)
from app.city_compliance.models import CitySpec

# Per-city outcome phrasing (must match coverage.product_mode).
_OUTCOME_FOCUS: dict[str, str] = {
    "mn": (
        "licensed for Minneapolis, Minnesota (Hennepin County) rental "
        "(plus violations and condemned/boarded flags)"
    ),
    "sea": "registered under Seattle RRIO rental registration",
    "nyc": "registered with NYC HPD and clear of open HMC violations",
    "chi": "showing open Chicago building code violations (not rental license status)",
    "den": "licensed for Denver short-term rental",
    "sf": "showing San Francisco DBI notices of violation (not rental license status)",
    "lax": "showing open LA building & safety code cases (not rental license status)",
    "bos": "showing Boston building/property violations (not rental license status)",
    "phi": "showing Philadelphia L&I violations (not rental license status)",
    "orl": "licensed for Orlando short-term rental",
    "nola": "licensed for New Orleans short-term rental",
    "moco": "licensed under Montgomery County housing licensing without open violations",
    "gain": "showing open Gainesville code enforcement cases (not rental license status)",
    "kc": "showing open Kansas City exterior building violations (not rental license status)",
    "atx": "licensed for Austin short-term rental",
    "bna": "licensed for Nashville short-term rental",
    "sd": "licensed for San Diego short-term rental",
    "atl": "placeholder — no live licensing feed (verdict will be unknown)",
    "mia": "placeholder — no live licensing feed (verdict will be unknown)",
}


def mn_resource_description() -> str:
    """Canonical /mn/property-check Bazaar text (CDP <=500, discovery keywords)."""
    return (
        "Is this Minneapolis, Minnesota (Hennepin) address licensed for rental? "
        "One GET, $0.01 USDC (x402 on Base): normalized verdict, rental license "
        "status/tier/units/expiration, violation and condemned/boarded flags, "
        "JSON with source_url — not raw ArcGIS. Tenant screening, landlord DD, "
        "lending. Free sample: /mn/property-check/sample."
    )[:500]


def _violations_only_description(*, code: str, name: str, focus: str) -> str:
    return (
        f"Does this {name} address {focus}? "
        "One call, $0.01 USDC on Base (x402): returns violations_open or "
        "no_violations_found verdict, summary, case counts, source_url — "
        "**does not determine rental license or STR legality**. "
        f"product_mode=violations_only. Free sample: GET /us/{code}/property-check/sample."
    )[:500]


def _none_description(*, code: str, name: str) -> str:
    return (
        f"{name} property-check preview endpoint (product_mode=none): no live "
        "open-data licensing feed is wired yet; paid calls return verdict=unknown "
        "with low confidence — not evidence of unlicensed rental. "
        f"$0.01 USDC shape test: GET /us/{code}/property-check/sample."
    )[:500]


def paid_route_description(
    *,
    code: str,
    name: str,
    focus: str | None = None,
) -> str:
    """Bazaar / 402 description (<=500 chars, outcome-first, coverage-accurate)."""
    mode = product_mode_for_city(code, None)
    question = focus or _OUTCOME_FOCUS.get(
        code,
        "aligned with local rental and housing compliance records",
    )
    if mode == MODE_NONE:
        return _none_description(code=code, name=name)
    if mode == MODE_VIOLATIONS_ONLY:
        return _violations_only_description(code=code, name=name, focus=question)
    return (
        f"Is this {name} address {question}? "
        "One call, $0.01 USDC on Base (x402): returns normalized verdict, "
        "one-sentence summary, key license dates when the feed includes them, "
        "open violation count when joined, confidence, data_as_of, source_url, "
        "plus raw rows under records. "
        f"Free fixed-address shape check: GET /us/{code}/property-check/sample."
    )[:500]


def for_spec(spec: CitySpec) -> str:
    if spec.code == "mn":
        return mn_resource_description()
    return paid_route_description(code=spec.code, name=spec.name)


def mcp_city_check_blurb() -> str:
    return (
        "Paid US city property check ($0.01 USDC, x402): returns verdict, product_mode, "
        "and coverage_note — licensing cities answer licensed/not_licensed; "
        "violations-only cities answer violations_open/no_violations_found only. "
        "Call city.list → city.sample → city.check."
    )


def mcp_city_list_blurb() -> str:
    return (
        "List US cities with paid_url, sample_url, and product_mode (license vs "
        "violations_only). Each lookup is $0.01 and returns a scope-aware verdict."
    )


def mcp_city_sample_blurb() -> str:
    return (
        "Free fixed-address preview of paid property-check JSON (verdict, product_mode, "
        "coverage_note, schema). Use before city.check."
    )


def agent_skill_summary(city_entry: dict[str, str]) -> str:
    code = city_entry["code"]
    name = city_entry["name"]
    state = city_entry["state"]
    mode = product_mode_for_city(code, None)
    focus = _OUTCOME_FOCUS.get(code, "compliant with local housing records")
    price = city_entry.get("price", "$0.01")
    paid = city_entry.get("paid_url", "")
    sample = city_entry.get("sample_url", "")
    sample_addr = city_entry.get("sample_address", "")
    if mode == MODE_VIOLATIONS_ONLY:
        lead = f"Open code violations at this {name}, {state} address? (Not a license check.)"
    elif mode == MODE_NONE:
        lead = f"{name}, {state} preview only — no live feed; verdict stays unknown."
    else:
        lead = f"Is this {name}, {state} address {focus}?"
    return (
        f"{lead} One paid call ({price} USDC, x402) → verdict, product_mode, source link. "
        f"Paid: {paid}?address=<street>. "
        f"Free sample (fixed {sample_addr!r}): {sample}."
    )
