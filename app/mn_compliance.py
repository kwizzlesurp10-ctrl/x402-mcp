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

import base64
import json
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

LICENSE_FIELDS = (
    "address,apn,licenseNumber,category,tier,status,issueDate,expirationDate,"
    "licensedUnits,ownerName,ward,neighborhoodDesc,communityDesc,shortTermRental"
)
VIOLATION_FIELDS = (
    "APN,Violation_Case_Number,Case_Type,Case_Group,Inspection_Result,"
    "Inspection_Type_Desc,Start_Date,Completed_Date"
)
CONDEMNED_FIELDS = "APN,Address,VBR_Date,CONB,Ward,Neighborho"

RESOURCE_DESCRIPTION = (
    "Minneapolis rental property compliance check: active rental license "
    "(status, tier, licensed units, expiration), regulatory violation case "
    "history, and condemned/boarded status for a street address. "
    "Live City of Minneapolis open data."
)


def _escape(value: str) -> str:
    """Escape a value for an ArcGIS SQL where clause (single-quote doubling)."""
    return value.replace("'", "''")


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
    needle = _escape(address.strip().upper())

    async with httpx.AsyncClient(timeout=25.0) as client:
        licenses = await _query(
            client,
            "Active_Rental_Licenses",
            f"UPPER(address) LIKE '{needle}%'",
            LICENSE_FIELDS,
            10,
        )

        apns = sorted({l["apn"] for l in licenses if l.get("apn")})
        violations: list[dict] = []
        condemned: list[dict] = []
        if apns:
            apn_list = ", ".join(f"'{_escape(a)}'" for a in apns)
            violations = await _query(
                client,
                "CaseViolations",
                f"APN IN ({apn_list})",
                VIOLATION_FIELDS,
                200,
            )
            condemned = await _query(
                client,
                "Condemned_by_Boarding",
                f"APN IN ({apn_list})",
                CONDEMNED_FIELDS,
                10,
            )
        else:
            # No license found — still check condemned/boarded by address so a
            # completely unlicensed problem property is not reported as clean.
            condemned = await _query(
                client,
                "Condemned_by_Boarding",
                f"UPPER(Address) LIKE '{needle}%'",
                CONDEMNED_FIELDS,
                10,
            )

    recent_violations = sorted(
        violations, key=lambda v: v.get("Start_Date") or 0, reverse=True
    )[:10]

    return {
        "address_queried": address.strip(),
        "rental_licenses": [
            {
                "address": l.get("address"),
                "apn": l.get("apn"),
                "license_number": l.get("licenseNumber"),
                "status": l.get("status"),
                "tier": l.get("tier"),
                "category": l.get("category"),
                "licensed_units": l.get("licensedUnits"),
                "owner_name": l.get("ownerName"),
                "issue_date": _iso(l.get("issueDate")),
                "expiration_date": _iso(l.get("expirationDate")),
                "ward": l.get("ward"),
                "neighborhood": l.get("neighborhoodDesc"),
                "community": l.get("communityDesc"),
                "short_term_rental": l.get("shortTermRental"),
            }
            for l in licenses
        ],
        "licensed": bool(licenses),
        "violation_cases": {
            "total": len(violations),
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
            "flagged": bool(condemned),
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


# ---- x402 seller gate -------------------------------------------------------


def resource_url() -> str:
    return f"{settings.public_base_url}/mn/property-check"


def build_payment_required_header() -> str:
    """Base64 x402 v2 PAYMENT-REQUIRED header for this resource."""
    from x402 import PaymentRequired, ResourceInfo

    from app.models import BuildSellerRequirementsInput
    from app.x402_services import build_seller_requirements

    built = build_seller_requirements(
        BuildSellerRequirementsInput(
            network=settings.x402_default_network,
            price=settings.mn_property_check_price,
            description=RESOURCE_DESCRIPTION,
        )
    )
    payment_required = PaymentRequired(
        x402_version=2,
        error="Payment required",
        resource=ResourceInfo(
            url=resource_url(),
            description=RESOURCE_DESCRIPTION,
            mime_type="application/json",
        ),
        accepts=built["requirements"],
    )
    wire = payment_required.model_dump(by_alias=True, exclude_none=True)
    return base64.b64encode(json.dumps(wire).encode()).decode()


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
