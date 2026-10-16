"""Server-authored payment terms for Pro tier and tool-credit purchases.

Commerce activate/purchase must never verify against caller-supplied
``payment_required`` blobs. Challenges are issued by
``build_pro_upgrade_requirements`` / ``build_tool_credits_requirements``,
cached per agent (and credit pack), and enforced before verify+settle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from app.agent_surface import BASE_USDC
from app.config import settings

logger = logging.getLogger("commerce_payment")

CommercePurpose = Literal["pro_tier_upgrade", "tool_credits"]

# Base Sepolia USDC (SDK registry may not resolve the "USDC" symbol on testnet).
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


@dataclass(frozen=True)
class StoredCommerceChallenge:
    purpose: CommercePurpose
    agent_id: str
    payment_required_header: str
    credits: int | None = None


# In-memory challenge cache (mirrors swarm product storage; Redis not required).
_pro_challenges: dict[str, StoredCommerceChallenge] = {}
_credits_challenges: dict[tuple[str, int], StoredCommerceChallenge] = {}


def _price_to_atomic(price: str) -> int:
    raw = str(price).strip().replace("$", "").replace(",", "")
    try:
        return int(round(float(raw) * 1_000_000))
    except ValueError:
        return 0


def expected_usdc_asset(network: str) -> str:
    """Canonical USDC contract for EVM revenue networks."""
    if network == "eip155:8453":
        return BASE_USDC
    if network == "eip155:84532":
        return BASE_SEPOLIA_USDC
    if network.startswith("eip155:"):
        try:
            from x402.mechanisms.evm.utils import get_asset_info

            info = get_asset_info(network, BASE_USDC)
            return str(info["address"])
        except Exception:  # noqa: BLE001
            return BASE_USDC
    return BASE_USDC


def _normalize_address(addr: str | None) -> str:
    if not addr:
        return ""
    return str(addr).strip().lower()


def _requirement_amount_atomic(req: dict[str, Any]) -> int | None:
    amount = req.get("amount")
    if amount is None:
        return None
    try:
        return int(str(amount).strip())
    except (TypeError, ValueError):
        return None


def validate_commerce_requirements(
    requirements: list[dict[str, Any]],
    *,
    min_amount_atomic: int,
    expected_network: str | None = None,
    expected_pay_to: str | None = None,
) -> None:
    """Fail closed if any served accept option violates revenue policy."""
    pay_to = expected_pay_to or settings.x402_pay_to_address
    if not pay_to:
        raise ValueError("X402_PAY_TO_ADDRESS required for commerce payments.")

    from app.x402_services import resolve_revenue_network

    network = expected_network or resolve_revenue_network()
    expected_asset = expected_usdc_asset(network)
    pay_norm = _normalize_address(pay_to)
    asset_norm = _normalize_address(expected_asset)

    if not requirements:
        raise ValueError("commerce payment requirements missing accepts[]")

    for req in requirements:
        req_net = str(req.get("network") or "")
        if req_net != network:
            raise ValueError(
                f"commerce payment network mismatch: expected {network}, got {req_net}"
            )
        if _normalize_address(req.get("pay_to") or req.get("payTo")) != pay_norm:
            raise ValueError("commerce payment pay_to does not match configured cashier")
        req_asset = _normalize_address(req.get("asset"))
        if req_asset not in (asset_norm, "usdc"):
            raise ValueError("commerce payment asset must be USDC on the revenue network")
        amount = _requirement_amount_atomic(req)
        if amount is None or amount < min_amount_atomic:
            raise ValueError(
                f"commerce payment amount below minimum ({min_amount_atomic} atomic units)"
            )


def _requirements_from_built(built: dict[str, Any]) -> list[dict[str, Any]]:
    reqs = built.get("requirements") or []
    return [r for r in reqs if isinstance(r, dict)]


def store_pro_challenge(agent_id: str, built: dict[str, Any]) -> None:
    header = built.get("payment_required_header")
    if not header:
        raise ValueError("pro upgrade requirements missing payment_required_header")
    _pro_challenges[agent_id] = StoredCommerceChallenge(
        purpose="pro_tier_upgrade",
        agent_id=agent_id,
        payment_required_header=header,
    )


def store_credits_challenge(agent_id: str, credits: int, built: dict[str, Any]) -> None:
    header = built.get("payment_required_header")
    if not header:
        raise ValueError("tool credits requirements missing payment_required_header")
    _credits_challenges[(agent_id, credits)] = StoredCommerceChallenge(
        purpose="tool_credits",
        agent_id=agent_id,
        payment_required_header=header,
        credits=credits,
    )


def clear_commerce_challenges() -> None:
    """Test helper: reset in-memory challenge cache."""
    _pro_challenges.clear()
    _credits_challenges.clear()


def resolve_pro_authoritative_header(
    agent_id: str,
    *,
    rebuild: Any,
) -> StoredCommerceChallenge:
    stored = _pro_challenges.get(agent_id)
    if stored is None:
        rebuild()
        stored = _pro_challenges.get(agent_id)
    if stored is None:
        raise ValueError("failed to issue pro-tier payment challenge")

    validate_commerce_requirements(
        _requirements_from_header(stored.payment_required_header),
        min_amount_atomic=_price_to_atomic(settings.pro_tier_price),
    )
    return stored


def resolve_credits_authoritative_header(
    agent_id: str,
    credits: int,
    *,
    rebuild: Any,  # noqa: ARG001 — kept for API symmetry; credits must be pre-issued
) -> StoredCommerceChallenge:
    stored = _credits_challenges.get((agent_id, credits))
    if stored is None:
        pending = [
            ch for (aid, _pack), ch in _credits_challenges.items() if aid == agent_id
        ]
        if len(pending) == 1:
            stored = pending[0]
        else:
            raise ValueError(
                "No tool-credit payment challenge on file for this agent/pack. "
                "Call commerce.credits_requirements, pay, then commerce.purchase_credits."
            )

    reqs = _requirements_from_header(stored.payment_required_header)
    validate_commerce_requirements(
        reqs,
        min_amount_atomic=_price_to_atomic(settings.tool_credit_pack_price),
    )
    return stored


def _requirements_from_header(payment_required_header: str) -> list[dict[str, Any]]:
    from x402.http import decode_payment_required_header

    pr = decode_payment_required_header(payment_required_header)
    accepts = list(getattr(pr, "accepts", []) or [])
    return [
        a.model_dump() if hasattr(a, "model_dump") else dict(a) for a in accepts
    ]


def credits_to_grant(challenge: StoredCommerceChallenge, caller_credits: int) -> int:
    """Paid pack size from the server challenge — never caller-inflated credits."""
    if challenge.purpose != "tool_credits":
        raise ValueError("not a tool credits challenge")
    granted = challenge.credits
    if granted is None or granted <= 0:
        granted = settings.tool_credit_pack_size
    if caller_credits != granted:
        raise ValueError(
            f"credit pack mismatch: payment was for {granted} credits, "
            f"caller requested {caller_credits}"
        )
    return granted
