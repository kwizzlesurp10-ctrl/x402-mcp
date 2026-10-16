"""Security tests: commerce Pro/credits must verify server-authored payment terms."""

from __future__ import annotations

import base64
import json

import pytest

from app import x402_services
from app.commerce import InMemoryQuotaStore
from app.commerce_payment import (
    clear_commerce_challenges,
    credits_to_grant,
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


def test_credits_to_grant_rejects_inflated_pack() -> None:
    from app.commerce_payment import StoredCommerceChallenge

    ch = StoredCommerceChallenge(
        purpose="tool_credits",
        agent_id="a1",
        payment_required_header="e30=",
        credits=25,
    )
    with pytest.raises(ValueError, match="pack mismatch"):
        credits_to_grant(ch, 9999)


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
    pack = 25
    built = x402_services.build_tool_credits_requirements(agent, pack)
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
    pack = 25
    x402_services.build_tool_credits_requirements(agent, pack)

    async def fake_settle(params):
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0x1"},
        }

    monkeypatch.setattr(x402_services, "_verify_and_settle_payment", fake_settle)
    monkeypatch.setattr(x402_services, "quota_store", InMemoryQuotaStore())

    with pytest.raises(ValueError, match="pack mismatch"):
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
