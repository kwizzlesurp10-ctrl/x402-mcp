"""Dataclasses for a swarm run: purchases, the composite product, and the run log."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Candidate:
    """An upstream x402 service the scout surfaced for possible purchase."""

    url: str
    price_usdc: float | None
    network: str | None
    source: str  # "bazaar" | "config"
    title: str = ""


@dataclass
class Purchase:
    """A settled (or attempted) upstream buy — the cost basis of the composite."""

    url: str
    amount_usdc: float
    amount_usdc_atomic: int
    network: str
    settled: bool
    tx: str | None
    preview: str
    title: str = ""


@dataclass
class CompositeProduct:
    """The resold artifact: composed from N upstream buys, priced off cost basis."""

    product_id: str
    topic: str
    cost_basis_usdc: float
    price_usdc: float
    markup: float
    network: str
    sources: list[str]
    report: str
    status: str = "draft"  # draft | listed | sold
    seller_requirements: dict[str, Any] | None = None
    revenue_usdc: float = 0.0
    ltv_cac_projected: float = 0.0
    run_id: str | None = None
    seller_agent_id: str | None = None
    # When the report was synthesized (ISO-8601, UTC). The Pulse is sold as
    # *live* network economics, so a restored snapshot needs a way to know it
    # has gone stale. None means "written before this field existed" — treated
    # as stale so the first restore after upgrading refreshes it.
    created_at: str | None = None

    @property
    def margin_usdc(self) -> float:
        return round(self.price_usdc - self.cost_basis_usdc, 6)


def purchase_discovery_metadata(
    product: CompositeProduct, public_base_url: str
) -> dict[str, Any]:
    """Bazaar discovery fields for a product's payable purchase endpoint.

    Passed into BuildSellerRequirementsInput so the served 402 challenge carries
    the resource URL + bazaar extension the CDP facilitator catalogs on settle.
    GET is the canonical purchase method (the endpoint accepts GET and POST);
    the output example mirrors the 200 body of /swarm/products/{id}/purchase.
    """
    base = public_base_url.rstrip("/")
    report_preview = product.report.splitlines()[0] if product.report else ""
    return {
        "resource_url": f"{base}/swarm/products/{product.product_id}/purchase",
        "discovery_method": "GET",
        "discovery_output_example": {
            "product_id": product.product_id,
            "topic": product.topic,
            "report": report_preview,
            "payment_settled": True,
        },
    }


@dataclass
class SwarmRun:
    """Full audit trail of one buy → compose → list cycle."""

    run_id: str
    topic: str
    agent_id: str
    status: str  # scouting | buying | composing | listing | listed | failed
    started_ts: str
    finished_ts: str | None = None
    candidates: list[Candidate] = field(default_factory=list)
    vetoes: list[dict[str, str]] = field(default_factory=list)
    purchases: list[Purchase] = field(default_factory=list)
    product: CompositeProduct | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
