"""Server-authored payment terms for Pro tier and tool-credit purchases.

Commerce activate/purchase must never verify against caller-supplied
``payment_required`` blobs. Challenges are issued by
``build_pro_upgrade_requirements`` / ``build_tool_credits_requirements``,
cached with server-generated ids (bounded TTL), and enforced before verify+settle.
Settlement tx hashes are deduped (Redis SETNX when available).
"""

from __future__ import annotations

import logging
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal

from app.agent_surface import BASE_USDC
from app.config import settings

logger = logging.getLogger("commerce_payment")

CommercePurpose = Literal["pro_tier_upgrade", "tool_credits"]

CHALLENGE_TTL_SECONDS = 900
CHALLENGE_MAX_ENTRIES = 512
SETTLEMENT_DEDUPE_TTL_SECONDS = 40 * 24 * 3600

# Base Sepolia USDC (SDK registry may not resolve the "USDC" symbol on testnet).
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


@dataclass(frozen=True)
class StoredCommerceChallenge:
    challenge_id: str
    purpose: CommercePurpose
    agent_id: str
    payment_required_header: str
    credits: int | None
    expires_at: float


_challenges: OrderedDict[str, StoredCommerceChallenge] = OrderedDict()
_pending_by_agent: dict[tuple[CommercePurpose, str], str] = {}
_mem_settled_txs: set[str] = set()


def normalize_credit_pack(credits: int | None) -> int:
    """Only the configured pack size is sold at ``tool_credit_pack_price``."""
    pack = settings.tool_credit_pack_size
    if credits is not None and credits != pack:
        raise ValueError(
            f"unsupported credit pack size {credits}; "
            f"only {pack} credits per pack is sold"
        )
    return pack


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


def _purge_challenge_cache() -> None:
    now = time.time()
    for challenge_id in list(_challenges.keys()):
        ch = _challenges.get(challenge_id)
        if ch is not None and ch.expires_at <= now:
            _challenges.pop(challenge_id, None)
            _pending_by_agent.pop((ch.purpose, ch.agent_id), None)
    while len(_challenges) > CHALLENGE_MAX_ENTRIES:
        challenge_id, ch = _challenges.popitem(last=False)
        _pending_by_agent.pop((ch.purpose, ch.agent_id), None)


def _insert_challenge(
    purpose: CommercePurpose,
    agent_id: str,
    payment_required_header: str,
    credits: int | None,
) -> StoredCommerceChallenge:
    _purge_challenge_cache()
    pending_key = (purpose, agent_id)
    old_id = _pending_by_agent.get(pending_key)
    if old_id:
        _challenges.pop(old_id, None)

    challenge_id = secrets.token_hex(16)
    ch = StoredCommerceChallenge(
        challenge_id=challenge_id,
        purpose=purpose,
        agent_id=agent_id,
        payment_required_header=payment_required_header,
        credits=credits,
        expires_at=time.time() + CHALLENGE_TTL_SECONDS,
    )
    while len(_challenges) >= CHALLENGE_MAX_ENTRIES:
        _, evicted = _challenges.popitem(last=False)
        _pending_by_agent.pop((evicted.purpose, evicted.agent_id), None)

    _pending_by_agent[pending_key] = challenge_id
    _challenges[challenge_id] = ch
    return ch


def store_pro_challenge(agent_id: str, built: dict[str, Any]) -> StoredCommerceChallenge:
    header = built.get("payment_required_header")
    if not header:
        raise ValueError("pro upgrade requirements missing payment_required_header")
    ch = _insert_challenge("pro_tier_upgrade", agent_id, header, None)
    built["commerce_challenge_id"] = ch.challenge_id
    return ch


def store_credits_challenge(
    agent_id: str, credits: int, built: dict[str, Any]
) -> StoredCommerceChallenge:
    header = built.get("payment_required_header")
    if not header:
        raise ValueError("tool credits requirements missing payment_required_header")
    pack = normalize_credit_pack(credits)
    ch = _insert_challenge("tool_credits", agent_id, header, pack)
    built["commerce_challenge_id"] = ch.challenge_id
    built["credits"] = pack
    return ch


def consume_challenge(challenge: StoredCommerceChallenge) -> None:
    """Drop a challenge after successful fulfillment (one-time use)."""
    _challenges.pop(challenge.challenge_id, None)
    _pending_by_agent.pop((challenge.purpose, challenge.agent_id), None)


def clear_commerce_challenges() -> None:
    """Test helper: reset in-memory challenge cache and settlement dedupe."""
    _challenges.clear()
    _pending_by_agent.clear()
    _mem_settled_txs.clear()


def clear_commerce_settlement_dedupe() -> None:
    """Test helper: reset in-process settlement dedupe only."""
    _mem_settled_txs.clear()


def _redis_client() -> Any | None:
    if not settings.redis_url:
        return None
    try:
        import redis

        return redis.Redis.from_url(settings.redis_url, decode_responses=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("commerce settlement dedupe: redis unavailable (%s)", exc)
        return None


def record_commerce_settlement(purpose: CommercePurpose, tx: str | None) -> bool:
    """Register a settlement tx; False if this tx was already fulfilled for purpose.

    Matches swarm ``record_settlement``: ``tx=None`` is always accepted (no dedupe).
    """
    if not tx:
        return True
    mem_key = f"{purpose}:{tx}"
    client = _redis_client()
    if client is not None:
        try:
            redis_key = f"commerce:settled:{purpose}:{tx}"
            return bool(
                client.set(redis_key, "1", nx=True, ex=SETTLEMENT_DEDUPE_TTL_SECONDS)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("commerce settlement dedupe redis failed: %s", exc)
    if mem_key in _mem_settled_txs:
        return False
    _mem_settled_txs.add(mem_key)
    return True


def settlement_tx_from_payment(payment: dict[str, Any]) -> str | None:
    settlement = payment.get("settlement") or {}
    if not isinstance(settlement, dict):
        return None
    tx = (
        settlement.get("transaction")
        or settlement.get("tx_hash")
        or settlement.get("txHash")
        or settlement.get("transactionHash")
    )
    return str(tx) if tx else None


def _get_pending_challenge(
    purpose: CommercePurpose, agent_id: str
) -> StoredCommerceChallenge | None:
    _purge_challenge_cache()
    challenge_id = _pending_by_agent.get((purpose, agent_id))
    if not challenge_id:
        return None
    ch = _challenges.get(challenge_id)
    if ch is None:
        _pending_by_agent.pop((purpose, agent_id), None)
        return None
    if ch.expires_at <= time.time():
        consume_challenge(ch)
        return None
    return ch


def resolve_pro_authoritative_header(
    agent_id: str,
    *,
    rebuild: Any,
) -> StoredCommerceChallenge:
    stored = _get_pending_challenge("pro_tier_upgrade", agent_id)
    if stored is None:
        rebuild()
        stored = _get_pending_challenge("pro_tier_upgrade", agent_id)
    if stored is None:
        raise ValueError("failed to issue pro-tier payment challenge")

    validate_commerce_requirements(
        _requirements_from_header(stored.payment_required_header),
        min_amount_atomic=_price_to_atomic(settings.pro_tier_price),
    )
    return stored


def resolve_credits_authoritative_header(
    agent_id: str,
    credits: int | None,
    *,
    rebuild: Any,  # noqa: ARG001
) -> StoredCommerceChallenge:
    pack = normalize_credit_pack(credits)
    stored = _get_pending_challenge("tool_credits", agent_id)
    if stored is None:
        raise ValueError(
            "No tool-credit payment challenge on file for this agent. "
            "Call commerce.credits_requirements, pay, then commerce.purchase_credits."
        )
    if stored.credits != pack:
        raise ValueError(
            f"credit pack mismatch: payment was for {stored.credits} credits, "
            f"caller requested {pack}"
        )

    validate_commerce_requirements(
        _requirements_from_header(stored.payment_required_header),
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


def credits_to_grant(challenge: StoredCommerceChallenge) -> int:
    """Paid pack size from the server challenge."""
    if challenge.purpose != "tool_credits":
        raise ValueError("not a tool credits challenge")
    granted = challenge.credits
    if granted is None or granted <= 0:
        granted = settings.tool_credit_pack_size
    return granted
