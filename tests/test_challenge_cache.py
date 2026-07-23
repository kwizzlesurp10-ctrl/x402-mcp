"""The 402 challenge survives a facilitator outage, so the storefront keeps
selling. Without the cache, one CDP 502 turned every unpaid request into a 500 —
a healthy box that can't sell.
"""

from __future__ import annotations

import fakeredis
import pytest

from app import challenge_cache, redis_client


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(challenge_cache, "_mem", {})
    monkeypatch.setattr(redis_client, "client", None)


def test_builds_once_then_serves_from_cache() -> None:
    calls = {"n": 0}

    def build():
        calls["n"] += 1
        return "HDR-1"

    assert challenge_cache.get_or_build("r", "fp1", build) == "HDR-1"
    assert challenge_cache.get_or_build("r", "fp1", build) == "HDR-1"
    assert calls["n"] == 1  # second call did not touch the facilitator


def test_a_facilitator_outage_serves_last_known_good() -> None:
    """The whole point: once built, a 502 does not stop us selling."""
    assert challenge_cache.get_or_build("r", "fp1", lambda: "HDR-1") == "HDR-1"

    def boom():
        raise RuntimeError("Facilitator get_supported failed (502)")

    # same fingerprint would serve cache without calling build; force a rebuild
    # attempt with a new fingerprint to prove the failure path degrades.
    assert challenge_cache.get_or_build("r", "fp2", boom) == "HDR-1"


def test_cold_start_with_no_cache_reraises() -> None:
    """Nothing ever cached + facilitator down -> caller turns this into a 503."""
    def boom():
        raise RuntimeError("502")

    with pytest.raises(RuntimeError):
        challenge_cache.get_or_build("never", "fp", boom)


def test_a_changed_fingerprint_rebuilds() -> None:
    """A reprice must not be served the old challenge forever."""
    assert challenge_cache.get_or_build("r", "price-0.01", lambda: "OLD") == "OLD"
    assert challenge_cache.get_or_build("r", "price-0.05", lambda: "NEW") == "NEW"
    # and the new one is now the cached value
    assert challenge_cache.get_or_build("r", "price-0.05", lambda: "unused") == "NEW"


def test_header_survives_a_restart_via_redis(monkeypatch) -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "client", client)

    challenge_cache.get_or_build("r", "fp1", lambda: "HDR-1")

    # fresh process: memory cleared, same Redis, facilitator still down
    monkeypatch.setattr(challenge_cache, "_mem", {})

    def boom():
        raise RuntimeError("502 on cold start")

    assert challenge_cache.get_or_build("r", "fp-different", boom) == "HDR-1"


def test_the_live_tx_decision_builder_uses_the_cache(monkeypatch) -> None:
    """End to end: a build failure on tx-decision degrades, does not raise,
    once a header has been cached."""
    from app import tx_decision, x402_services
    from app.config import settings

    monkeypatch.setattr(challenge_cache, "_mem", {})
    monkeypatch.setattr(settings, "x402_pay_to_address", "0xabc")
    monkeypatch.setattr(
        x402_services,
        "build_seller_requirements",
        lambda params: {"payment_required_header": "GOOD-HDR"},
    )
    assert tx_decision.build_payment_required_header() == "GOOD-HDR"

    def boom(params):
        raise RuntimeError("Facilitator get_supported failed (502)")

    monkeypatch.setattr(x402_services, "build_seller_requirements", boom)
    # price unchanged -> same fingerprint -> cache hit, never even calls build
    assert tx_decision.build_payment_required_header() == "GOOD-HDR"
