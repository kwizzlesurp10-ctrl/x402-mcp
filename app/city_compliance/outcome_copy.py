"""Outcome-first discovery copy for US city property-check products."""

from __future__ import annotations

from app.city_compliance.models import CitySpec

# Per-city question the buyer is really asking (accurate to adapter scope).
_OUTCOME_FOCUS: dict[str, str] = {
    "mn": (
        "licensed for Minneapolis, Minnesota (Hennepin County) rental "
        "(plus violations and condemned/boarded flags)"
    ),
    "sea": "registered under Seattle RRIO rental registration",
    "nyc": "registered with NYC HPD and clear of open HMC violations",
    "chi": "showing open Chicago building code violations at this address",
    "den": "licensed for Denver short-term rental",
    "sf": "showing active San Francisco DBI notices of violation",
    "lax": "showing open Los Angeles building & safety code enforcement cases",
    "bos": "showing Boston building/property violations for this address",
    "phi": "showing Philadelphia L&I property maintenance violations",
    "orl": "licensed for Orlando short-term rental",
    "nola": "licensed for New Orleans short-term rental",
    "moco": "licensed under Montgomery County housing licensing without open violations",
    "gain": "showing open Gainesville code enforcement cases",
    "kc": "showing open Kansas City exterior building violations",
    "atx": "licensed for Austin short-term rental",
    "bna": "licensed for Nashville short-term rental",
    "sd": "licensed for San Diego short-term rental",
    "atl": "licensed for Atlanta short-term rental",
    "mia": "licensed for Miami short-term rental",
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


def paid_route_description(
    *,
    code: str,
    name: str,
    focus: str | None = None,
) -> str:
    """Bazaar / 402 description (<=500 chars, outcome-first)."""
    question = focus or _OUTCOME_FOCUS.get(
        code,
        "aligned with local rental and housing compliance records",
    )
    return (
        f"Is this {name} address {question}? "
        "One call, $0.01 USDC on Base (x402): returns normalized verdict, "
        "one-sentence summary, key license dates, open violation count when the "
        "city feed includes it, confidence, data_as_of freshness, source_url to "
        "the city's record, plus raw rows under records. "
        f"Free fixed-address shape check: GET /us/{code}/property-check/sample."
    )[:500]


def for_spec(spec: CitySpec) -> str:
    if spec.code == "mn":
        return mn_resource_description()
    return paid_route_description(code=spec.code, name=spec.name)


def mcp_city_check_blurb() -> str:
    return (
        "Paid US city property compliance: is this address licensed / flagged / "
        "showing open violations? One city.check call ($0.01 USDC, x402 on Base) "
        "returns verdict + summary + source_url — skip stitching Socrata/ArcGIS "
        "yourself. Call city.list, then city.sample (free shape), then city.check."
    )


def mcp_city_list_blurb() -> str:
    return (
        "List 17 US cities with paid_url and free sample_url for property compliance. "
        "Start here before city.sample or city.check — each paid lookup is $0.01 "
        "and returns a normalized verdict instead of raw portal JSON."
    )


def mcp_city_sample_blurb() -> str:
    return (
        "Free fixed-address preview of the paid property-check JSON (verdict, summary, "
        "schema). Use before city.check to validate parsing without spending $0.01."
    )


def agent_skill_summary(city_entry: dict[str, str]) -> str:
    code = city_entry["code"]
    name = city_entry["name"]
    state = city_entry["state"]
    focus = _OUTCOME_FOCUS.get(code, "compliant with local housing records")
    price = city_entry.get("price", "$0.01")
    paid = city_entry.get("paid_url", "")
    sample = city_entry.get("sample_url", "")
    sample_addr = city_entry.get("sample_address", "")
    return (
        f"Is this {name}, {state} address {focus}? "
        f"One paid call ({price} USDC, x402) → verdict, summary, dates, source link. "
        f"Paid: {paid}?address=<street>. "
        f"Free sample (fixed {sample_addr!r}): {sample}."
    )
