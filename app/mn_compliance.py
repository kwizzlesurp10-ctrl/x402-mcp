"""MN property compliance product: paid x402 HTTP resource.

Composite rental-compliance snapshot for a Minneapolis address, sourced live
from the City of Minneapolis Open Data ArcGIS services (public records):

- Active_Rental_Licenses  — license status/tier/units/expiry, joined by APN to
- CaseViolations          — regulatory-services violation case inspections
- Condemned_by_Boarding   — condemned / boarded properties

One paid call answers "is this rental licensed, and does it have a violation
or condemnation history?" — the seller side of this repo's own protocol
tooling (requirements built and settled via the same x402ResourceServer path
as the pro-tier / tool-credit flows).

Owner phone/email exist in the source data but are intentionally not served.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

# ---- TTL cache for ArcGIS responses ----------------------------------------
# Avoids re-hitting the city endpoint for repeated queries within the window.
# Keyed on normalised address; entries expire after _CACHE_TTL seconds.

_CACHE_TTL = 900  # 15 minutes
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_get(key: str) -> dict[str, Any] | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, data = entry
    if time.monotonic() - ts > _CACHE_TTL:
        _cache.pop(key, None)
        return None
    return data


def _cache_set(key: str, data: dict[str, Any]) -> None:
    _cache[key] = (time.monotonic(), data)

LICENSE_FIELDS = (
    "address,apn,licenseNumber,category,tier,status,issueDate,expirationDate,"
    "licensedUnits,ownerName,ward,neighborhoodDesc,communityDesc,shortTermRental"
)
VIOLATION_FIELDS = (
    "APN,Display,Violation_Case_Number,Case_Type,Case_Group,Inspection_Result,"
    "Inspection_Type_Desc,Start_Date,Completed_Date"
)

# City ArcGIS stores USPS abbreviations (AVE, ST, N). Paying agents often send
# Avenue / North / dotted "Ave." and used to get a false `unlicensed` after
# settlement. Token map is word-boundary only so STREET does not become STreet.
_STREET_TOKEN_MAP = {
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
    "AVENUE": "AVE",
    "STREET": "ST",
    "BOULEVARD": "BLVD",
    "DRIVE": "DR",
    "ROAD": "RD",
    "LANE": "LN",
    "COURT": "CT",
    "PLACE": "PL",
    "TERRACE": "TER",
    "PARKWAY": "PKWY",
    "HIGHWAY": "HWY",
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
    "APARTMENT": "APT",
    "SUITE": "STE",
}
CONDEMNED_FIELDS = "APN,Address,VBR_Date,CONB,Ward,Neighborho"

# Written query-shaped, and this matters more here than anywhere else in the
# repo: a discovery catalog indexes the description ONCE, at the settle that
# first catalogs the resource, and never revisits it. The words below are the
# only words a buying agent can match on. So it leads with the question a buyer
# actually asks, names the locality the way people write it (Minneapolis /
# Minnesota / Hennepin County), and names the jobs this gets hired for --
# rather than describing the endpoint to another engineer.
#
# 500 chars is the CDP ceiling (_clamp_description); this sits under it.
RESOURCE_DESCRIPTION = (
    "Minneapolis rental license check — is this property licensed? Property due "
    "diligence agent for Minneapolis Minnesota (Hennepin) housing compliance open "
    "data. GET ?address= (street 1-120 chars) → compliance_verdict "
    "(licensed_clean|licensed_with_violations|unlicensed|condemned_or_boarded), "
    "rental license status/tier/units/expiration, violation cases, condemned/"
    "boarded. Live City JSON. Tenant screening, landlord DD, lending. Sample: "
    "/mn/property-check/sample."
)

# Per-resource Bazaar metadata (facilitator: name <=32, <=5 tags x <=32 chars).
# Must NOT inherit the storefront defaults (base,intelligence) — those describe
# Base L2 fee products, not Minneapolis rental compliance, and agents filter
# catalogs by these tags. Fingerprinted into the challenge cache.
SERVICE_NAME = "MN Rental License Check"
SERVICE_TAGS = ["minneapolis", "rental-license", "compliance", "housing", "diligence"]


def _escape(value: str) -> str:
    """Escape a value for an ArcGIS SQL where clause (single-quote doubling)."""
    return value.replace("'", "''")


def normalize_street_query(address: str) -> str:
    """USPS-abbreviate a Minneapolis street query to match city ArcGIS rows."""
    cleaned = address.strip().upper()
    cleaned = cleaned.replace(".", " ").replace(",", " ").replace("#", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    return " ".join(_STREET_TOKEN_MAP.get(token, token) for token in cleaned.split())


def _select_license_matches(
    licenses: list[dict], *, normalized: str, query: str
) -> tuple[list[dict], dict[str, Any]]:
    """Prefer an exact normalized address over a prefix mash of other parcels."""
    exact = [
        row
        for row in licenses
        if normalize_street_query(str(row.get("address") or "")) == normalized
    ]
    if exact:
        chosen = exact
        mode = "exact"
    elif licenses:
        chosen = licenses
        mode = "prefix"
    else:
        chosen = []
        mode = "none"
    matched_addresses = [str(row.get("address") or "") for row in chosen]
    too_broad = bool(normalized) and not any(ch.isalpha() for ch in normalized)
    return chosen, {
        "query": query,
        "normalized": normalized,
        "mode": mode,
        "hit_count": len(chosen),
        "ambiguous": len(chosen) > 1,
        "too_broad": too_broad,
        "matched_addresses": matched_addresses,
    }


def _iso(epoch_ms: Any) -> str | None:
    if not isinstance(epoch_ms, (int, float)):
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).date().isoformat()


async def _query(
    client: httpx.AsyncClient, dataset: str, where: str, out_fields: str, limit: int
) -> list[dict]:
    response = await client.get(
        f"{settings.mn_data_base_url}/{dataset}/FeatureServer/0/query",
        params={
            "where": where,
            "outFields": out_fields,
            "resultRecordCount": limit,
            "returnGeometry": "false",
            "f": "json",
        },
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise ValueError(f"{dataset} query error: {payload['error']}")
    return [f["attributes"] for f in payload.get("features", [])]


async def check_property(address: str) -> dict[str, Any]:
    """Compose the compliance report for a Minneapolis street address."""
    query = address.strip()
    normalized = normalize_street_query(query)
    cache_key = normalized or query.upper()

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    sql_needle = _escape(normalized)
    licenses: list[dict] = []
    match: dict[str, Any]
    violations: list[dict] = []
    condemned: list[dict] = []

    async with httpx.AsyncClient(timeout=25.0) as client:
        if sql_needle:
            licenses_raw = await _query(
                client,
                "Active_Rental_Licenses",
                f"UPPER(address) LIKE '{sql_needle}%'",
                LICENSE_FIELDS,
                10,
            )
        else:
            licenses_raw = []
        licenses, match = _select_license_matches(
            licenses_raw, normalized=normalized, query=query
        )

        apns = sorted({row["apn"] for row in licenses if row.get("apn")})
        if apns:
            apn_list = ", ".join(f"'{_escape(a)}'" for a in apns)
            violations, condemned = await asyncio.gather(
                _query(
                    client,
                    "CaseViolations",
                    f"APN IN ({apn_list})",
                    VIOLATION_FIELDS,
                    200,
                ),
                _query(
                    client,
                    "Condemned_by_Boarding",
                    f"APN IN ({apn_list})",
                    CONDEMNED_FIELDS,
                    10,
                ),
            )
        elif sql_needle:
            # No license APN — still join violations + condemned by address so a
            # completely unlicensed problem property is not reported as clean.
            violations, condemned = await asyncio.gather(
                _query(
                    client,
                    "CaseViolations",
                    f"UPPER(Display) LIKE '{sql_needle}%'",
                    VIOLATION_FIELDS,
                    200,
                ),
                _query(
                    client,
                    "Condemned_by_Boarding",
                    f"UPPER(Address) LIKE '{sql_needle}%'",
                    CONDEMNED_FIELDS,
                    10,
                ),
            )

    recent_violations = sorted(
        violations, key=lambda v: v.get("Start_Date") or 0, reverse=True
    )[:10]

    licensed = bool(licenses)
    condemned_flagged = bool(condemned)
    violation_total = len(violations)
    open_total = sum(1 for row in violations if row.get("Completed_Date") is None)
    # One-token decision for agent buyers. Severity order: condemned >
    # unlicensed > licensed-with-history > clean. Derived only from the
    # three ArcGIS joins above — no scoring model. Historical (completed)
    # cases still flag licensed_with_violations; buyers use open_total to
    # separate live inspections from closed history.
    if condemned_flagged:
        compliance_verdict = "condemned_or_boarded"
    elif not licensed:
        compliance_verdict = "unlicensed"
    elif violation_total > 0:
        compliance_verdict = "licensed_with_violations"
    else:
        compliance_verdict = "licensed_clean"

    report = {
        "address_queried": query,
        "compliance_verdict": compliance_verdict,
        "match": match,
        "rental_licenses": [
            {
                "address": row.get("address"),
                "apn": row.get("apn"),
                "license_number": row.get("licenseNumber"),
                "status": row.get("status"),
                "tier": row.get("tier"),
                "category": row.get("category"),
                "licensed_units": row.get("licensedUnits"),
                "owner_name": row.get("ownerName"),
                "issue_date": _iso(row.get("issueDate")),
                "expiration_date": _iso(row.get("expirationDate")),
                "ward": row.get("ward"),
                "neighborhood": row.get("neighborhoodDesc"),
                "community": row.get("communityDesc"),
                "short_term_rental": row.get("shortTermRental"),
            }
            for row in licenses
        ],
        "licensed": licensed,
        "violation_cases": {
            "total": violation_total,
            "open_total": open_total,
            "recent": [
                {
                    "case_number": v.get("Violation_Case_Number"),
                    "case_type": v.get("Case_Type"),
                    "case_group": v.get("Case_Group"),
                    "inspection_result": v.get("Inspection_Result"),
                    "inspection_type": v.get("Inspection_Type_Desc"),
                    "start_date": _iso(v.get("Start_Date")),
                    "completed_date": _iso(v.get("Completed_Date")),
                }
                for v in recent_violations
            ],
        },
        "condemned_or_boarded": {
            "flagged": condemned_flagged,
            "records": [
                {
                    "address": c.get("Address"),
                    "apn": c.get("APN"),
                    "vbr_date": c.get("VBR_Date"),
                    "condemned_by_boarding": c.get("CONB"),
                    "ward": c.get("Ward"),
                    "neighborhood": c.get("Neighborho"),
                }
                for c in condemned
            ],
        },
        "sources": [
            f"{settings.mn_data_base_url}/Active_Rental_Licenses/FeatureServer/0",
            f"{settings.mn_data_base_url}/CaseViolations/FeatureServer/0",
            f"{settings.mn_data_base_url}/Condemned_by_Boarding/FeatureServer/0",
        ],
        "disclaimer": (
            "Public records from City of Minneapolis Open Data, served as-is; "
            "not legal advice. Verify with the city before acting."
        ),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
    }

    _cache_set(cache_key, report)
    return report


# ---- x402 seller gate -------------------------------------------------------


def resource_url() -> str:
    return f"{settings.public_base_url}/mn/property-check"


# Free sample address: same shape as a paid response, fixed so the free path
# cannot substitute for the paid product (any other address still requires
# payment). Used by GET /mn/property-check/sample and discovery docs.
SAMPLE_ADDRESS = "1700 Penn Ave N"

# Bazaar discovery examples: buyers call GET {resource_url}?address=... and
# receive a report shaped like check_property()'s output. Small but faithful
# excerpts — the CDP facilitator catalogs these verbatim at settle time.
DISCOVERY_INPUT_EXAMPLE: dict[str, Any] = {"address": SAMPLE_ADDRESS}

DISCOVERY_OUTPUT_EXAMPLE: dict[str, Any] = {
    "address_queried": "1700 Penn Ave N",
    "compliance_verdict": "licensed_with_violations",
    "licensed": True,
    "match": {
        "query": "1700 Penn Ave N",
        "normalized": "1700 PENN AVE N",
        "mode": "exact",
        "hit_count": 1,
        "ambiguous": False,
        "too_broad": False,
        "matched_addresses": ["1700 PENN AVE N"],
    },
    "rental_licenses": [
        {
            "address": "1700 PENN AVE N",
            "apn": "1602924320087",
            "license_number": "LIC394217",
            "status": "Active",
            "tier": "Tier 1",
            "category": "CONV",
            "licensed_units": 1,
            "expiration_date": "2027-03-01",
            "ward": "5",
            "neighborhood": "Willard - Hay",
        }
    ],
    "violation_cases": {
        "total": 1,
        "open_total": 0,
        "recent": [
            {
                "case_number": "CE1263963",
                "case_type": "HIS",
                "inspection_result": "AdminMon",
                "start_date": "2021-05-03",
            }
        ],
    },
    "condemned_or_boarded": {"flagged": False, "records": []},
    "disclaimer": "Public records from City of Minneapolis Open Data.",
    "generated_at": "2026-07-16T00:00:00+00:00",
}


def build_payment_required_header() -> str:
    """Base64 x402 v2 PAYMENT-REQUIRED header for this resource.

    Delegates to build_seller_requirements so the challenge carries
    ResourceInfo plus (per BAZAAR_DISCOVERABLE) the Bazaar discovery
    extension — without it a settled payment through the CDP facilitator
    catalogs nothing and this product stays invisible to buyers.
    """
    from app import challenge_cache
    from app.models import BuildSellerRequirementsInput
    from app.x402_services import build_seller_requirements

    network = settings.x402_default_network
    price = settings.mn_property_check_price
    # Fingerprint MUST include every input baked into the cached header —
    # including per-resource Bazaar service_name/tags and the payTo cashier.
    # Omitting any of them freezes a wrong value into Redis (and into Bazaar on
    # the next settle); omitting pay_to keeps settling to a retired address.
    fp = challenge_cache.fingerprint(
        network=network,
        price=price,
        resource=resource_url(),
        pay_to=settings.x402_pay_to_address,
        discoverable=settings.bazaar_discoverable,
        description=RESOURCE_DESCRIPTION,
        input_example=DISCOVERY_INPUT_EXAMPLE,
        output_example=DISCOVERY_OUTPUT_EXAMPLE,
        service_name=SERVICE_NAME,
        service_tags=SERVICE_TAGS,
    )

    def _build() -> str:
        return build_seller_requirements(
            BuildSellerRequirementsInput(
                network=network,
                price=price,
                description=RESOURCE_DESCRIPTION,
                resource_url=resource_url(),
                mime_type="application/json",
                discovery_method="GET",
                discovery_input_example=DISCOVERY_INPUT_EXAMPLE,
                discovery_output_example=DISCOVERY_OUTPUT_EXAMPLE,
                service_name=SERVICE_NAME,
                service_tags=SERVICE_TAGS,
            )
        )["payment_required_header"]

    # Cached per (network, price, resource): the header is static and building
    # it hits the flaky CDP facilitator; serve last-known-good through an outage.
    return challenge_cache.get_or_build("mn-property-check", fp, _build)


async def verify_and_settle(payment_signature: str, payment_required: str) -> dict:
    """Verify + settle an incoming payment for this resource."""
    from app.models import VerifyPaymentInput
    from app.x402_services import _verify_and_settle_payment

    return await _verify_and_settle_payment(
        VerifyPaymentInput(
            payment_signature=payment_signature,
            payment_required=payment_required,
        )
    )
