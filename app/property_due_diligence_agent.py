"""$0.01 Property due diligence agent — discoverable single-address check.

Fresh resource URL so CDP can index buyer-query copy that frozen city SKUs
cannot refresh. Reuses city_compliance / mn open-data joins.
"""

from __future__ import annotations

from typing import Any

from app.city_compliance import registry
from app.config import settings

PRODUCT_ID = "property-due-diligence-agent"
SERVICE_NAME = "Property Due Diligence Agent"  # 28 chars
SERVICE_TAGS = ["diligence", "agent", "housing", "compliance", "rental"]
PRICE = "$0.01"

RESOURCE_DESCRIPTION = (
    "Property due diligence agent for US housing compliance open data. "
    "Is this property licensed? Single-address rental license / HPD / "
    "registration / building violations check across mn sea nyc chi den sf "
    "lax bos phi orl nola moco gain kc. GET ?city_code=&address= → "
    "compliance_verdict + license/violation fields (JSON). Tenant screening, "
    "landlord DD, lending. $0.01 USDC on Base."
)

DISCOVERY_INPUT_EXAMPLE: dict[str, Any] = {
    "city_code": "mn",
    "address": "1700 Penn Ave N",
}

DISCOVERY_OUTPUT_EXAMPLE: dict[str, Any] = {
    "product_id": PRODUCT_ID,
    "payment_settled": True,
    "city": "mn",
    "city_name": "Minneapolis",
    "state": "MN",
    "address_queried": "1700 Penn Ave N",
    "compliance_verdict": "licensed_with_violations",
    "agent": "property-due-diligence",
}


def resource_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}/agent/property-due-diligence"


def build_payment_required_header() -> str:
    from app import challenge_cache
    from app.models import BuildSellerRequirementsInput
    from app.x402_services import build_seller_requirements

    network = settings.x402_default_network
    res = resource_url()
    tags = list(SERVICE_TAGS)
    fp = challenge_cache.fingerprint(
        network=network,
        price=PRICE,
        resource=res,
        discoverable=settings.bazaar_discoverable,
        description=RESOURCE_DESCRIPTION,
        input_example=DISCOVERY_INPUT_EXAMPLE,
        output_example=DISCOVERY_OUTPUT_EXAMPLE,
        service_name=SERVICE_NAME,
        service_tags=tags,
    )

    def _build() -> str:
        return build_seller_requirements(
            BuildSellerRequirementsInput(
                network=network,
                price=PRICE,
                description=RESOURCE_DESCRIPTION,
                resource_url=res,
                mime_type="application/json",
                discovery_method="GET",
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


async def run_check(*, city_code: str, address: str) -> dict[str, Any]:
    code = (city_code or "").strip().lower()
    if code not in registry.CITIES:
        raise KeyError(code)
    mod = registry.get_city(code)
    report = await mod.check_property(address)
    if not isinstance(report, dict):
        report = {"result": report}
    out = dict(report)
    out.setdefault("city", code)
    out["product_id"] = PRODUCT_ID
    out["payment_settled"] = True
    out["agent"] = "property-due-diligence"
    return out
