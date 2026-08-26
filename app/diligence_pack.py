"""US Multi-City Rental Diligence Pack — paid A2A composite task.

POST /tasks/us-rental-diligence
  Unpaid → 402 + Bazaar-discoverable PAYMENT-REQUIRED
  Paid   → verify/settle, then reuse city open-data checks (access barrier).

Priced $0.75–$2.50 (default $1.50). Not a free-RPC wrapper — PRODUCT-FOCUS.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.city_compliance.registry import CITIES, get_city
from app.config import settings

log = logging.getLogger("x402")

PRODUCT_ID = "us-rental-diligence-pack"
SERVICE_NAME = "Property Due Diligence Pack"  # <=32
SERVICE_TAGS = ["due-diligence", "housing", "compliance", "multicity", "agent"]

CITY_CODES = tuple(sorted(CITIES.keys()))
CityCode = Literal[
    "mn",
    "sea",
    "nyc",
    "chi",
    "den",
    "sf",
    "lax",
    "bos",
    "phi",
    "orl",
    "nola",
    "moco",
    "gain",
    "kc",
]

RESOURCE_DESCRIPTION = (
    "Property due diligence agent pack: multi-city batch housing compliance open "
    "data. POST properties[{city_code,address}] (1-5) → per-address "
    "compliance_verdict + pack risk_summary in one x402 settle ($1.50 USDC). "
    "Portfolio screen across mn sea nyc chi den sf lax bos phi orl nola moco gain "
    "kc. Not the single-address $0.01 tier — those stay at /us/{code}/property-check."
)

DISCOVERY_INPUT_EXAMPLE: dict[str, Any] = {
    "properties": [
        {"city_code": "mn", "address": "1700 Penn Ave N"},
        {"city_code": "sea", "address": "1531 BELMONT AVE"},
    ],
    "include_base_pulse_context": False,
}

DISCOVERY_OUTPUT_EXAMPLE: dict[str, Any] = {
    "product_id": PRODUCT_ID,
    "payment_settled": True,
    "pack_id": "example-pack-id",
    "price_usdc": 1.5,
    "property_count": 2,
    "ok_count": 2,
    "risk_summary": {
        "overall": "mixed",
        "flagged": 1,
        "clean": 1,
        "errors": 0,
    },
    "properties": [
        {
            "city_code": "mn",
            "address": "1700 Penn Ave N",
            "ok": True,
            "compliance_verdict": "licensed_with_violations",
        }
    ],
    "generated_at": "2026-08-16T00:00:00+00:00",
}


class PropertyQuery(BaseModel):
    city_code: str = Field(..., min_length=1, max_length=16)
    address: str = Field(..., min_length=1, max_length=120)

    @field_validator("city_code")
    @classmethod
    def _norm_city(cls, v: str) -> str:
        code = (v or "").strip().lower()
        if code not in CITIES:
            raise ValueError(
                f"unknown city_code {v!r}; expected one of {', '.join(CITY_CODES)}"
            )
        return code

    @field_validator("address")
    @classmethod
    def _strip_address(cls, v: str) -> str:
        s = (v or "").strip()
        if not s or len(s) > 120:
            raise ValueError("address must be 1-120 chars")
        return s


class DiligencePackRequest(BaseModel):
    properties: list[PropertyQuery] = Field(..., min_length=1)
    include_base_pulse_context: bool = False
    idempotency_key: str | None = Field(default=None, max_length=64)

    @field_validator("properties")
    @classmethod
    def _cap_properties(cls, v: list[PropertyQuery]) -> list[PropertyQuery]:
        max_n = int(settings.diligence_pack_max_properties)
        if len(v) > max_n:
            raise ValueError(f"at most {max_n} properties per pack")
        return v


def resource_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}/tasks/us-rental-diligence"


def parse_price_usdc(price_str: str | None = None) -> float:
    raw = price_str if price_str is not None else settings.diligence_pack_price
    try:
        return float(str(raw).replace("$", "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid diligence_pack_price {raw!r}") from exc


def validated_price_usdc() -> float:
    """Return pack price or raise if outside [min, max] clamp."""
    price = parse_price_usdc()
    lo = float(settings.diligence_pack_min_usdc)
    hi = float(settings.diligence_pack_max_usdc)
    if price < lo or price > hi:
        raise ValueError(
            f"diligence_pack_price ${price:.2f} outside clamp "
            f"[${lo:.2f}, ${hi:.2f}]"
        )
    return price


def price_string() -> str:
    return f"${validated_price_usdc():.2f}"


def build_payment_required_header() -> str:
    """Base64 x402 v2 PAYMENT-REQUIRED for the diligence pack (POST body)."""
    from app import challenge_cache
    from app.models import BuildSellerRequirementsInput
    from app.x402_services import build_seller_requirements

    network = settings.x402_default_network
    price = price_string()
    res = resource_url()
    tags = list(SERVICE_TAGS)
    fp = challenge_cache.fingerprint(
        network=network,
        price=price,
        resource=res,
        discoverable=settings.bazaar_discoverable,
        description=RESOURCE_DESCRIPTION,
        input_example=DISCOVERY_INPUT_EXAMPLE,
        output_example=DISCOVERY_OUTPUT_EXAMPLE,
        service_name=SERVICE_NAME,
        service_tags=tags,
        method="POST",
    )

    def _build() -> str:
        return build_seller_requirements(
            BuildSellerRequirementsInput(
                network=network,
                price=price,
                description=RESOURCE_DESCRIPTION,
                resource_url=res,
                mime_type="application/json",
                discovery_method="POST",
                discovery_input_example=DISCOVERY_INPUT_EXAMPLE,
                discovery_output_example=DISCOVERY_OUTPUT_EXAMPLE,
                service_name=SERVICE_NAME,
                service_tags=tags,
            )
        )["payment_required_header"]

    return challenge_cache.get_or_build(PRODUCT_ID, fp, _build)


async def verify_and_settle(payment_signature: str, payment_required: str) -> dict:
    from app.models import VerifyPaymentInput
    from app.x402_services import _verify_and_settle_payment

    return await _verify_and_settle_payment(
        VerifyPaymentInput(
            payment_signature=payment_signature,
            payment_required=payment_required,
        )
    )


def _verdict_bucket(report: dict[str, Any]) -> str:
    v = str(report.get("compliance_verdict") or "").lower()
    if v in ("condemned_or_boarded", "unlicensed"):
        return "flagged"
    if v in ("licensed_with_violations",):
        return "flagged"
    if v in ("licensed_clean", "clean", "registered", "no_violations"):
        return "clean"
    # Unknown / city-specific — treat missing verdict as neutral error path later
    if report.get("error"):
        return "error"
    if v:
        return "mixed"
    return "unknown"


async def check_one(city_code: str, address: str) -> dict[str, Any]:
    """Run one city check; never raises — item-level error envelope."""
    row: dict[str, Any] = {
        "city_code": city_code,
        "address": address,
        "ok": False,
    }
    try:
        mod = get_city(city_code)
        report = await mod.check_property(address)
        if not isinstance(report, dict):
            row["error"] = "invalid_report_shape"
            return row
        if report.get("error"):
            row["error"] = report.get("error")
            row["detail"] = report.get("detail")
            row["report"] = report
            return row
        row["ok"] = True
        row["compliance_verdict"] = report.get("compliance_verdict")
        row["report"] = report
        row["bucket"] = _verdict_bucket(report)
        return row
    except Exception as exc:  # noqa: BLE001 — pack must deliver after pay
        log.warning(
            "diligence pack city check failed city=%s: %s",
            city_code,
            exc,
            exc_info=True,
        )
        row["error"] = "upstream_open_data_unavailable"
        row["detail"] = f"{type(exc).__name__}: {exc}"[:240]
        return row


def risk_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    flagged = clean = errors = unknown = 0
    for it in items:
        if not it.get("ok"):
            errors += 1
            continue
        b = it.get("bucket") or _verdict_bucket(it.get("report") or {})
        if b == "flagged":
            flagged += 1
        elif b == "clean":
            clean += 1
        else:
            unknown += 1
    if errors and not (flagged or clean or unknown):
        overall = "unavailable"
    elif flagged and clean:
        overall = "mixed"
    elif flagged:
        overall = "elevated_risk"
    elif clean and not unknown:
        overall = "clear"
    elif clean:
        overall = "mostly_clear"
    else:
        overall = "unknown"
    return {
        "overall": overall,
        "flagged": flagged,
        "clean": clean,
        "errors": errors,
        "unknown": unknown,
        "property_count": len(items),
    }


async def build_pack(
    body: DiligencePackRequest,
    *,
    payment_settled: bool,
    settlement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose the paid deliverable (or structure-only for tests)."""
    items: list[dict[str, Any]] = []
    for p in body.properties:
        items.append(await check_one(p.city_code, p.address))

    pulse_context: dict[str, Any] | None = None
    if body.include_base_pulse_context:
        try:
            from app import pulse

            data = await pulse.get_pulse()
            # Compact free context — not sold alone
            pulse_context = {
                "latest_block": data.get("latest_block"),
                "verdict": (data.get("assessment") or {}).get("verdict"),
                "eth_price_usd": data.get("eth_price_usd"),
                "generated_at": data.get("generated_at"),
            }
        except Exception as exc:  # noqa: BLE001
            pulse_context = {
                "error": "pulse_unavailable",
                "detail": f"{type(exc).__name__}: {exc}"[:160],
            }

    pack_id = (body.idempotency_key or "").strip() or uuid.uuid4().hex
    price = validated_price_usdc()
    out: dict[str, Any] = {
        "product_id": PRODUCT_ID,
        "payment_settled": payment_settled,
        "pack_id": pack_id,
        "price_usdc": price,
        "price": f"${price:.2f}",
        "network": settings.x402_default_network,
        "property_count": len(items),
        "ok_count": sum(1 for i in items if i.get("ok")),
        "risk_summary": risk_summary(items),
        "properties": items,
        "sources": {
            "catalog": f"{settings.public_base_url.rstrip('/')}/us/cities",
            "single_address_tier": "/us/{code}/property-check",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }
    if pulse_context is not None:
        out["pulse_context"] = pulse_context
    if settlement:
        out["settlement_tx"] = settlement.get("transaction") or settlement.get("txHash")
    return out
