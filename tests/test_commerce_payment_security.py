"""Security tests: commerce Pro/credits must verify server-authored payment terms."""

from __future__ import annotations

import base64
import json
import time

import pytest

from app import x402_services
from app.commerce import InMemoryQuotaStore
from app.commerce_payment import (
    CHALLENGE_MAX_ENTRIES,
    clear_commerce_challenges,
    credits_to_grant,
    normalize_credit_pack,
    record_commerce_settlement,
    validate_commerce_requirements,
)
from app.config import settings


@pytest.fixture(autouse=True)
def _reset_commerce_challenges() -> None:
    clear_commerce_challenges()
    yield
    clear_commerce_challenges()


@pytest.fixture
def pay_to(monkeypatch: pytest.MonkeyPatch) -> str:
    addr = "0xTestPayTo00000000000000000000000001"
    monkeypatch.setattr(settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(settings, "x402_default_network", "eip155:84532")
    return addr


def _evil_payment_required_header(
    *,
    pay_to: str,
    network: str = "eip155:84532",
    amount_atomic: int = 1,
) -> str:
    """Minimal attacker-controlled PAYMENT-REQUIRED blob (tiny / wrong payTo)."""
    from x402.http import encode_payment_required_header
    from x402.schemas import PaymentRequired, PaymentRequirements

    req = PaymentRequirements(
        scheme="exact",
        network=network,
        pay_to=pay_to,
        amount=str(amount_atomic),
        asset="USDC",
        max_timeout_seconds=300,
        extra={},
    )
    return encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="evil")
    )


def test_normalize_credit_pack_rejects_non_default() -> None:
    with pytest.raises(ValueError, match="unsupported credit pack"):
        normalize_credit_pack(25)


def test_build_tool_credits_rejects_custom_pack(pay_to: str) -> None:
    with pytest.raises(ValueError, match="unsupported credit pack"):
        x402_services.build_tool_credits_requirements("agent-x", 50)


def test_validate_rejects_underpay(pay_to: str) -> None:
    reqs = [
        {
            "scheme": "exact",
            "network": "eip155:84532",
            "pay_to": pay_to,
            "amount": "1",
            "asset": "USDC",
        }
    ]
    min_atomic = int(round(29.0 * 1_000_000))
    with pytest.raises(ValueError, match="amount below minimum"):
        validate_commerce_requirements(reqs, min_amount_atomic=min_atomic)


def test_validate_rejects_wrong_pay_to(pay_to: str) -> None:
    reqs = [
        {
            "scheme": "exact",
            "network": "eip155:84532",
            "pay_to": "0x" + "b" * 40,
            "amount": str(int(round(29.0 * 1_000_000))),
            "asset": "USDC",
        }
    ]
    with pytest.raises(ValueError, match="pay_to"):
        validate_commerce_requirements(
            reqs,
            min_amount_atomic=int(round(29.0 * 1_000_000)),
            expected_pay_to=pay_to,
        )


def test_validate_rejects_wrong_network(pay_to: str) -> None:
    reqs = [
        {
            "scheme": "exact",
            "network": "eip155:8453",
            "pay_to": pay_to,
            "amount": str(int(round(29.0 * 1_000_000))),
            "asset": "USDC",
        }
    ]
    with pytest.raises(ValueError, match="network mismatch"):
        validate_commerce_requirements(
            reqs,
            min_amount_atomic=int(round(29.0 * 1_000_000)),
            expected_network="eip155:84532",
            expected_pay_to=pay_to,
        )


def test_record_commerce_settlement_dedupes_in_memory() -> None:
    assert record_commerce_settlement("tool_credits", "0xabc") is True
    assert record_commerce_settlement("tool_credits", "0xabc") is False
    assert record_commerce_settlement("pro_tier_upgrade", "0xabc") is True


@pytest.mark.asyncio
async def test_activate_pro_ignores_caller_payment_required(
    pay_to: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = "security-pro-agent"
    built = x402_services.build_pro_upgrade_requirements(agent)
    server_header = built["payment_required_header"]
    evil = _evil_payment_required_header(pay_to="0x" + "aa" * 20, amount_atomic=1)

    seen_required: list[str] = []

    async def fake_settle(params):
        seen_required.append(params.payment_required)
        return {
            "is_valid": True,
            "invalid_reason": None,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0xpro"},
        }

    store = InMemoryQuotaStore()
    monkeypatch.setattr(x402_services, "quota_store", store)
    monkeypatch.setattr(x402_services, "_verify_and_settle_payment", fake_settle)

    result = await x402_services.activate_pro_tier("c2ln", evil, agent)

    assert result["activated"] is True
    assert store.get_tier(agent) == "pro"
    assert seen_required == [server_header]
    assert seen_required[0] != evil


@pytest.mark.asyncio
async def test_purchase_credits_ignores_caller_payment_required(
    pay_to: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = "security-credits-agent"
    pack = settings.tool_credit_pack_size
    built = x402_services.build_tool_credits_requirements(agent)
    server_header = built["payment_required_header"]
    evil = _evil_payment_required_header(pay_to="0x" + "cc" * 20, amount_atomic=1)

    seen_required: list[str] = []

    async def fake_settle(params):
        seen_required.append(params.payment_required)
        return {
            "is_valid": True,
            "invalid_reason": None,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0xcredits"},
        }

    store = InMemoryQuotaStore()
    monkeypatch.setattr(x402_services, "quota_store", store)
    monkeypatch.setattr(x402_services, "_verify_and_settle_payment", fake_settle)

    result = await x402_services.purchase_tool_credits("c2ln", evil, agent, pack)

    assert result["credited"] is True
    assert result["credits_purchased"] == pack
    assert store.get_credits(agent) == pack
    assert seen_required == [server_header]


@pytest.mark.asyncio
async def test_purchase_credits_rejects_inflated_credits_param(
    pay_to: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = "inflate-agent"
    x402_services.build_tool_credits_requirements(agent)

    async def fake_settle(params):
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0x1"},
        }

    monkeypatch.setattr(x402_services, "_verify_and_settle_payment", fake_settle)
    monkeypatch.setattr(x402_services, "quota_store", InMemoryQuotaStore())

    with pytest.raises(ValueError, match="unsupported credit pack"):
        await x402_services.purchase_tool_credits("c2ln", "ignored", agent, 9999)


@pytest.mark.asyncio
async def test_purchase_credits_without_challenge_fails(
    pay_to: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = "no-challenge-agent"

    async def fake_settle(params):
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True},
        }

    monkeypatch.setattr(x402_services, "_verify_and_settle_payment", fake_settle)

    with pytest.raises(ValueError, match="challenge on file"):
        await x402_services.purchase_tool_credits(
            "c2ln", "ignored", agent, settings.tool_credit_pack_size
        )


@pytest.mark.asyncio
async def test_purchase_credits_replay_does_not_double_credit(
    pay_to: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = "replay-credits"
    pack = settings.tool_credit_pack_size
    x402_services.build_tool_credits_requirements(agent)

    async def fake_settle(params):
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0xREPLAY"},
        }

    store = InMemoryQuotaStore()
    monkeypatch.setattr(x402_services, "quota_store", store)
    monkeypatch.setattr(x402_services, "_verify_and_settle_payment", fake_settle)

    first = await x402_services.purchase_tool_credits("sig", "ignored", agent, None)
    x402_services.build_tool_credits_requirements(agent)
    second = await x402_services.purchase_tool_credits("sig", "ignored", agent, None)

    assert first["credits_purchased"] == pack
    assert second.get("already_fulfilled") is True
    assert second["credits_purchased"] == 0
    assert store.get_credits(agent) == pack


@pytest.mark.asyncio
async def test_activate_pro_replay_is_idempotent(
    pay_to: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = "replay-pro"
    x402_services.build_pro_upgrade_requirements(agent)

    async def fake_settle(params):
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0xPROREPLAY"},
        }

    store = InMemoryQuotaStore()
    monkeypatch.setattr(x402_services, "quota_store", store)
    monkeypatch.setattr(x402_services, "_verify_and_settle_payment", fake_settle)

    first = await x402_services.activate_pro_tier("sig", "ignored", agent)
    x402_services.build_pro_upgrade_requirements(agent)
    second = await x402_services.activate_pro_tier("sig", "ignored", agent)

    assert first["activated"] is True
    assert second.get("already_fulfilled") is True
    assert store.get_tier(agent) == "pro"


@pytest.mark.asyncio
async def test_mutated_payment_required_header_not_used_for_verify(
    pay_to: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even a base64 JSON mutation in the caller blob must not reach verify."""
    agent = "mutate-agent"
    built = x402_services.build_pro_upgrade_requirements(agent)
    server_header = built["payment_required_header"]
    mutated = base64.b64encode(
        json.dumps({"accepts": [{"amount": "1"}], "x402Version": 2}).encode()
    ).decode()

    captured: list[str] = []

    async def fake_settle(params):
        captured.append(params.payment_required)
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0x1"},
        }

    monkeypatch.setattr(x402_services, "_verify_and_settle_payment", fake_settle)
    monkeypatch.setattr(x402_services, "quota_store", InMemoryQuotaStore())

    await x402_services.activate_pro_tier("sig", mutated, agent)
    assert captured[0] == server_header


@pytest.mark.asyncio
async def test_challenge_consumed_after_pro_activation(
    pay_to: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.commerce_payment import _get_pending_challenge

    agent = "consume-agent"
    x402_services.build_pro_upgrade_requirements(agent)
    assert _get_pending_challenge("pro_tier_upgrade", agent) is not None

    async def fake_settle(params):
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0xuse1"},
        }

    monkeypatch.setattr(x402_services, "_verify_and_settle_payment", fake_settle)
    monkeypatch.setattr(x402_services, "quota_store", InMemoryQuotaStore())

    await x402_services.activate_pro_tier("sig", "ignored", agent)
    assert _get_pending_challenge("pro_tier_upgrade", agent) is None


def test_challenge_cache_bounded(pay_to: str) -> None:
    from app.commerce_payment import _challenges

    for i in range(CHALLENGE_MAX_ENTRIES + 5):
        x402_services.build_pro_upgrade_requirements(f"agent-{i}")
    assert len(_challenges) <= CHALLENGE_MAX_ENTRIES


def test_credits_to_grant_uses_server_pack() -> None:
    from app.commerce_payment import StoredCommerceChallenge

    ch = StoredCommerceChallenge(
        challenge_id="c1",
        purpose="tool_credits",
        agent_id="a1",
        payment_required_header="e30=",
        credits=settings.tool_credit_pack_size,
        expires_at=time.time() + 60,
    )
    assert credits_to_grant(ch) == settings.tool_credit_pack_size
