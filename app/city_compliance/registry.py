"""Registry of US city compliance products (includes MN; excludes rewriting it)."""

from __future__ import annotations

from types import ModuleType
from typing import Any

from app.city_compliance.cities import (
    atl,
    atx,
    bna,
    bos,
    chi,
    den,
    gain,
    kc,
    lax,
    mia,
    mn,
    moco,
    nola,
    nyc,
    orl,
    phi,
    sd,
    sea,
    sf,
)
from app.city_compliance.models import CitySpec

# Import order is display order in /us/cities.
_MODULES: tuple[ModuleType, ...] = (
    mn,  # Minneapolis, MN (canonical /mn/property-check also)
    sea,  # Seattle, WA
    nyc,  # New York City, NY
    chi,  # Chicago, IL
    den,  # Denver, CO
    sf,  # San Francisco, CA
    lax,  # Los Angeles, CA
    bos,  # Boston, MA
    phi,  # Philadelphia, PA
    orl,  # Orlando, FL
    nola,  # New Orleans, LA
    moco,  # Montgomery County, MD
    gain,  # Gainesville, FL
    kc,  # Kansas City, MO
    atx,  # Austin, TX
    bna,  # Nashville, TN
    mia,  # Miami, FL
    atl,  # Atlanta, GA
    sd,  # San Diego, CA
)

CITIES: dict[str, ModuleType] = {m.SPEC.code: m for m in _MODULES}


def get_city(code: str) -> ModuleType:
    key = (code or "").strip().lower()
    if key not in CITIES:
        raise KeyError(key)
    return CITIES[key]


def public_modules() -> tuple[ModuleType, ...]:
    """Catalog / diligence / discovery set. Unpublished cities stay mounted."""
    return tuple(m for m in _MODULES if getattr(m.SPEC, "public", True))


def public_codes() -> tuple[str, ...]:
    return tuple(m.SPEC.code for m in public_modules())


def list_cities() -> list[dict[str, Any]]:
    from app.city_compliance import gate
    from app.config import settings

    base = settings.public_base_url.rstrip("/")
    out: list[dict[str, Any]] = []
    for mod in public_modules():
        spec: CitySpec = mod.SPEC
        out.append(
            {
                "code": spec.code,
                "name": spec.name,
                "state": spec.state,
                "service_name": spec.service_name,
                "price": gate.price_for(spec),
                "network": settings.x402_default_network,
                "paid_url": f"{base}/us/{spec.code}/property-check",
                "sample_url": f"{base}/us/{spec.code}/property-check/sample",
                "sample_address": spec.sample_address,
                "sources_label": spec.sources_label,
                "tags": list(spec.tags),
                "canonical_alias": "/mn/property-check" if spec.code == "mn" else None,
            }
        )
    return out


def known_codes() -> tuple[str, ...]:
    return tuple(m.SPEC.code for m in _MODULES)
