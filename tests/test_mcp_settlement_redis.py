"""MCP commerce settlement: Redis-backed coordination (fakeredis, no live Redis)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fakeredis
import pytest

from app import mcp_server, mcp_settlement_store, mcp_x402_payment, x402_services
from app.commerce import InMemoryQuotaStore
from app.commerce_payment import clear_commerce_challenges


@pytest.fixture
def pay_to(monkeypatch: pytest.MonkeyPatch) -> str:
    addr = "0xTestPayTo00000000000000000000000001"
    monkeypatch.setattr(mcp_x402_payment.settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(mcp_x402_payment.settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(mcp_x402_payment.settings, "x402_default_network", "eip155:84532")
    monkeypatch.setattr(mcp_x402_payment.settings, "mcp_commerce_redis_strict", True)
    monkeypatch.setattr(mcp_x402_payment.settings, "redis_url", "redis://mock")
    monkeypatch.setattr(x402_services.settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(x402_services.settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(x402_services.settings, "x402_default_network", "eip155:84532")
    return addr


def _fake_ctx(payment: dict | None) -> SimpleNamespace:
    from x402.mcp.constants import MCP_PAYMENT_META_KEY

    extra = {MCP_PAYMENT_META_KEY: payment} if payment is not None else {}
    meta = SimpleNamespace(model_extra=extra)
    request_context = SimpleNamespace(meta=meta)
    return SimpleNamespace(request_context=request_context)


def _valid_payload_dict(built: dict) -> dict:
    from x402.http import decode_payment_required_header

    pr = decode_payment_required_header(built["payment_required_header"])
    accept = pr.accepts[0]
    return {
        "x402Version": 2,
        "payload": {"signature": "0xsig", "authorization": {}},
        "accepted": accept.model_dump(by_alias=True, exclude_none=True),
    }


@pytest.fixture(autouse=True)
def _redis_settlement(monkeypatch: pytest.MonkeyPatch) -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(mcp_settlement_store, "_CLIENT", client)


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_commerce_challenges()
    mcp_x402_payment.clear_mcp_settlement_cache()
    if mcp_settlement_store._CLIENT:  # noqa: SLF001
        mcp_settlement_store.clear_mcp_settlement_redis_test()
    yield
    clear_commerce_challenges()
    mcp_x402_payment.clear_mcp_settlement_cache()


def _composite_from_built(built: dict, payment: dict) -> tuple[str, str]:
    from x402.schemas import PaymentPayload

    challenge = x402_services.resolve_pro_authoritative_header(
        "mcp-redis-dup",
        rebuild=lambda: x402_services.build_pro_upgrade_requirements("mcp-redis-dup"),
    )
    payload = PaymentPayload.model_validate(payment)
    ph = mcp_x402_payment._idempotency_key(payload)
    cf = mcp_settlement_store.challenge_fingerprint(challenge.payment_required_header)
    comp = mcp_settlement_store.composite_cache_key(ph, challenge.payment_required_header)
    return comp, cf


@pytest.mark.asyncio
async def test_two_workers_single_settle_via_redis_cache(
    pay_to: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = InMemoryQuotaStore()
    monkeypatch.setattr(mcp_server, "quota_store", store)
    monkeypatch.setattr(x402_services, "quota_store", store)

    built = x402_services.build_pro_upgrade_requirements("mcp-redis-dup")
    payment = _valid_payload_dict(built)

    mock_server = MagicMock()
    mock_server.find_matching_requirements = MagicMock(return_value=built["requirements"][0])
    mock_verify = MagicMock()
    mock_verify.is_valid = True
    mock_server.verify_payment = AsyncMock(return_value=mock_verify)
    mock_settle = MagicMock()
    mock_settle.success = True
    mock_settle.model_dump.return_value = {
        "success": True,
        "transaction": "0xredis_once",
        "network": "eip155:84532",
    }
    mock_server.settle_payment = AsyncMock(return_value=mock_settle)
    monkeypatch.setattr(x402_services, "_resource_server", lambda _net=None: mock_server)

    ctx = _fake_ctx(payment)
    first = await mcp_server.activate_pro_tier(agent_id="mcp-redis-dup", ctx=ctx)
    second = await mcp_server.activate_pro_tier(agent_id="mcp-redis-dup", ctx=ctx)

    assert first.isError is False
    assert second.isError is False
    assert mock_server.settle_payment.await_count == 1

    challenge = x402_services.resolve_pro_authoritative_header(
        "mcp-redis-dup",
        rebuild=lambda: x402_services.build_pro_upgrade_requirements("mcp-redis-dup"),
    )
    comp, cf = _composite_from_built(built, payment)
    body = mcp_settlement_store.get_cached_settlement(comp, expected_challenge_fp=cf)
    assert body is not None
    assert body["payment_settled"] is True


@pytest.mark.asyncio
async def test_contention_wait_returns_peer_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_x402_payment.settings, "x402_pay_to_address", "0x" + "ab" * 20)
    monkeypatch.setattr(x402_services.settings, "x402_pay_to_address", "0x" + "ab" * 20)
    monkeypatch.setattr(mcp_x402_payment.settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(x402_services.settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(mcp_x402_payment.settings, "x402_default_network", "eip155:84532")
    monkeypatch.setattr(x402_services.settings, "x402_default_network", "eip155:84532")
    monkeypatch.setattr(mcp_x402_payment.settings, "mcp_commerce_redis_strict", True)
    monkeypatch.setattr(mcp_x402_payment.settings, "redis_url", "redis://mock")

    built = x402_services.build_pro_upgrade_requirements("contention-wait")
    payment = _valid_payload_dict(built)
    challenge = x402_services.resolve_pro_authoritative_header(
        "contention-wait",
        rebuild=lambda: x402_services.build_pro_upgrade_requirements("contention-wait"),
    )
    from x402.schemas import PaymentPayload

    payload = PaymentPayload.model_validate(payment)
    ph = mcp_x402_payment._idempotency_key(payload)
    cf = mcp_settlement_store.challenge_fingerprint(challenge.payment_required_header)
    comp = mcp_settlement_store.composite_cache_key(ph, challenge.payment_required_header)

    peer_result = {
        "payment_settled": True,
        "settlement": {"success": True, "transaction": "0xpeer"},
        "is_valid": True,
    }
    clear_commerce_challenges()
    mcp_x402_payment.clear_mcp_settlement_cache()

    assert mcp_settlement_store.try_cache_settlement(
        comp, peer_result, challenge_fp=cf
    )

    def _no_lock(_c: str, *, ttl_seconds: int = 120) -> tuple[bool, str | None, bool]:
        return False, None, False

    monkeypatch.setattr(mcp_settlement_store, "acquire_settlement_lock", _no_lock)

    mock_server = MagicMock()
    mock_server.find_matching_requirements = MagicMock(return_value=built["requirements"][0])
    mock_server.verify_payment = AsyncMock()
    mock_server.settle_payment = AsyncMock()
    monkeypatch.setattr(x402_services, "_resource_server", lambda _net=None: mock_server)

    out = await mcp_x402_payment.verify_and_settle_mcp_payload(payment, challenge)
    assert out["payment_settled"] is True
    assert out["settlement"]["transaction"] == "0xpeer"
    mock_server.settle_payment.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_down_strict_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_x402_payment.settings, "redis_url", "redis://unreachable:9")
    monkeypatch.setattr(mcp_x402_payment.settings, "mcp_commerce_redis_strict", True)
    mcp_settlement_store.refresh_client()

    addr = "0x" + "cd" * 20
    monkeypatch.setattr(mcp_x402_payment.settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(x402_services.settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(mcp_x402_payment.settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(x402_services.settings, "revenue_network", "eip155:84532")

    built = x402_services.build_pro_upgrade_requirements("strict-fail")
    payment = _valid_payload_dict(built)
    challenge = x402_services.resolve_pro_authoritative_header(
        "strict-fail",
        rebuild=lambda: x402_services.build_pro_upgrade_requirements("strict-fail"),
    )
    out = await mcp_x402_payment.verify_and_settle_mcp_payload(payment, challenge)
    assert out["invalid_reason"] == "redis_unavailable_mcp_commerce"


@pytest.mark.asyncio
async def test_wrong_challenge_fingerprint_cache_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(mcp_settlement_store, "_CLIENT", client)
    monkeypatch.setattr(mcp_x402_payment.settings, "redis_url", "redis://x")
    monkeypatch.setattr(mcp_x402_payment.settings, "mcp_commerce_redis_strict", False)

    addr = "0x" + "ef" * 20
    monkeypatch.setattr(mcp_x402_payment.settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(x402_services.settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(mcp_x402_payment.settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(x402_services.settings, "revenue_network", "eip155:84532")

    built = x402_services.build_pro_upgrade_requirements("wrong-fp")
    payment = _valid_payload_dict(built)
    ch_a = x402_services.resolve_pro_authoritative_header(
        "wrong-fp",
        rebuild=lambda: x402_services.build_pro_upgrade_requirements("wrong-fp"),
    )
    from x402.schemas import PaymentPayload

    payload = PaymentPayload.model_validate(payment)
    ph = mcp_x402_payment._idempotency_key(payload)
    comp = mcp_settlement_store.composite_cache_key(ph, ch_a.payment_required_header)
    other_fp = "0" * 64
    mcp_settlement_store.try_cache_settlement(
        comp,
        {"payment_settled": True, "settlement": {"success": True, "transaction": "0xbad"}},
        challenge_fp=other_fp,
    )

    miss = mcp_settlement_store.get_cached_settlement(
        comp, expected_challenge_fp=mcp_settlement_store.challenge_fingerprint(
            ch_a.payment_required_header
        )
    )
    assert miss is None


@pytest.mark.asyncio
async def test_lock_token_does_not_delete_other_holder(monkeypatch: pytest.MonkeyPatch) -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(mcp_settlement_store, "_CLIENT", client)
    comp = "testlock:fp"
    ok1, tok1, err1 = mcp_settlement_store.acquire_settlement_lock(comp, ttl_seconds=300)
    assert ok1 and tok1 and not err1
    ok2, tok2, err2 = mcp_settlement_store.acquire_settlement_lock(comp, ttl_seconds=300)
    assert not ok2 and not err2
    mcp_settlement_store.release_settlement_lock(comp, "wrong-token")
    ok3, _, err3 = mcp_settlement_store.acquire_settlement_lock(comp, ttl_seconds=300)
    assert not ok3 and not err3
    mcp_settlement_store.release_settlement_lock(comp, tok1)
    ok4, tok4, err4 = mcp_settlement_store.acquire_settlement_lock(comp, ttl_seconds=300)
    assert ok4 and tok4 and not err4


@pytest.mark.asyncio
async def test_lock_acquire_redis_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_c: str, *, ttl_seconds: int = 120) -> tuple[bool, str | None, bool]:
        return False, None, True

    monkeypatch.setattr(mcp_settlement_store, "_CLIENT", object())
    monkeypatch.setattr(mcp_x402_payment.settings, "redis_url", "redis://mock")
    monkeypatch.setattr(mcp_x402_payment.settings, "mcp_commerce_redis_strict", True)
    monkeypatch.setattr(mcp_settlement_store, "acquire_settlement_lock", _boom)
    monkeypatch.setattr(mcp_settlement_store, "mcp_commerce_redis_ready", lambda: True)

    addr = "0x" + "11" * 20
    monkeypatch.setattr(mcp_x402_payment.settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(x402_services.settings, "x402_pay_to_address", addr)
    monkeypatch.setattr(mcp_x402_payment.settings, "revenue_network", "eip155:84532")
    monkeypatch.setattr(x402_services.settings, "revenue_network", "eip155:84532")

    built = x402_services.build_pro_upgrade_requirements("lock-err")
    payment = _valid_payload_dict(built)
    challenge = x402_services.resolve_pro_authoritative_header(
        "lock-err",
        rebuild=lambda: x402_services.build_pro_upgrade_requirements("lock-err"),
    )
    out = await mcp_x402_payment.verify_and_settle_mcp_payload(payment, challenge)
    assert out["invalid_reason"] == "redis_unavailable_mcp_commerce"
