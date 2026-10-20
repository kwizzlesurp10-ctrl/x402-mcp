"""Shared x402 challenge + settle path for US city network products.

Mirrors the MN product wire protocol (402-before-validation, fingerprint,
Bazaar discovery extension) without coupling to ``mn_compliance``.
"""

from __future__ import annotations

from typing import Any

from app.city_compliance.models import CitySpec
from app.config import settings


def resource_url(city: CitySpec) -> str:
    return f"{settings.public_base_url.rstrip('/')}/us/{city.code}/property-check"


def sample_url(city: CitySpec) -> str:
    return f"{resource_url(city)}/sample"


def product_id(city: CitySpec) -> str:
    return f"{city.product_id_prefix}-{city.code}-property-check"


def price_for(city: CitySpec) -> str:
    return getattr(settings, city.price_setting)


def build_payment_required_header(
    city: CitySpec,
    *,
    input_example: dict[str, Any],
    output_example: dict[str, Any],
) -> str:
    from app import challenge_cache
    from app.models import BuildSellerRequirementsInput
    from app.x402_services import build_seller_requirements

    network = settings.x402_default_network
    price = price_for(city)
    res = resource_url(city)
    tags = list(city.tags)
    fp = challenge_cache.fingerprint(
        network=network,
        price=price,
        resource=res,
        pay_to=settings.x402_pay_to_address,
        discoverable=settings.bazaar_discoverable,
        description=city.description,
        input_example=input_example,
        output_example=output_example,
        service_name=city.service_name,
        service_tags=tags,
    )

    def _build() -> str:
        return build_seller_requirements(
            BuildSellerRequirementsInput(
                network=network,
                price=price,
                description=city.description,
                resource_url=res,
                mime_type="application/json",
                discovery_method="GET",
                discovery_input_example=input_example,
                discovery_output_example=output_example,
                service_name=city.service_name,
                service_tags=tags,
            )
        )["payment_required_header"]

    return challenge_cache.get_or_build(product_id(city), fp, _build)


async def verify_and_settle(payment_signature: str, payment_required: str) -> dict:
    from app.models import VerifyPaymentInput
    from app.x402_services import _verify_and_settle_payment

    return await _verify_and_settle_payment(
        VerifyPaymentInput(
            payment_signature=payment_signature,
            payment_required=payment_required,
        )
    )
