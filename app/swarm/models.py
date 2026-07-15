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

    @property
    def margin_usdc(self) -> float:
        return round(self.price_usdc - self.cost_basis_usdc, 6)


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
