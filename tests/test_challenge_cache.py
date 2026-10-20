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


def test_a_description_change_busts_the_cache() -> None:
    """The bug this helper exists for: rewriting a catalog description changed
    the code, passed its tests, deployed, and never reached a buyer, because the
    hand-written fingerprint covered only network|price|resource|discoverable.
    The stale header survived in Redis across restarts — and a catalog indexes
    a description ONCE, so the stale text would have been frozen in permanently.
    """
    from app import challenge_cache

    common = dict(
        network="eip155:8453",
        price="$0.01",
        resource="https://host/mn/property-check",
        discoverable=True,
    )
    before = challenge_cache.fingerprint(**common, description="old text")
    after = challenge_cache.fingerprint(**common, description="new text")
    assert before != after


def test_every_builder_input_is_covered_by_the_fingerprint() -> None:
    """Not just the description — the discovery examples ride in the header too."""
    from app import challenge_cache

    base = dict(
        network="eip155:8453",
        price="$0.01",
        resource="https://host/r",
        pay_to="0x" + "a" * 40,
        discoverable=True,
        description="d",
        input_example={"address": "a"},
        output_example={"licensed": True},
        service_name="MN Rental Compliance",
        service_tags=["minneapolis", "rental"],
    )
    baseline = challenge_cache.fingerprint(**base)
    for field, changed in (
        ("network", "eip155:84532"),
        ("price", "$0.02"),
        ("resource", "https://host/other"),
        ("pay_to", "0x" + "b" * 40),
        ("discoverable", False),
        ("description", "different"),
        ("input_example", {"address": "b"}),
        ("output_example", {"licensed": False}),
        ("service_name", "Other Service"),
        ("service_tags", ["base", "intelligence"]),
    ):
        assert challenge_cache.fingerprint(**{**base, field: changed}) != baseline, (
            f"changing {field} did not bust the challenge cache"
        )


def test_a_payto_change_busts_every_product_cache(monkeypatch) -> None:
    """`pay_to` is baked into the header, so it must be in the fingerprint.

    `test_every_builder_input_is_covered_by_the_fingerprint` only exercises the
    `fingerprint()` helper, which hashes whatever it is handed — it cannot see a
    call site that forgets a field. `pay_to` was forgotten at all five revenue
    call sites while `main.py`'s `/demo/paid` fingerprint had it all along.

    The live consequence, observed on the deployed box 2026-09-13: the operator
    changed `X402_PAY_TO_ADDRESS` in the Render dashboard, the fingerprint did
    not move, and every cache-backed route kept serving a Redis-persisted 402
    that named the *previous* cashier. Buyers paid the old address, and the
    settles catalogued under the old merchant record, for weeks.

    This asserts on the fingerprint each builder actually passes, so it fails if
    a call site drops `pay_to` again.
    """
    from app import challenge_cache, x402_services
    from app.city_compliance import registry
    from app.config import settings

    seen: list[str] = []

    def _capture(name, fp, builder):  # noqa: ANN001 - test double
        seen.append(fp)
        return "HDR"

    monkeypatch.setattr(challenge_cache, "get_or_build", _capture)
    monkeypatch.setattr(
        x402_services,
        "build_seller_requirements",
        lambda params: {"payment_required_header": "HDR"},
    )

    mn = next(m for m in registry.public_modules() if m.SPEC.code == "mn")
    builders = {
        "city-gate": lambda: _city_gate_header(mn),
        "mn-property-check": _mn_header,
        "base-tx-decision": _tx_header,
        "us-rental-diligence-pack": _diligence_header,
        "property-due-diligence-agent": _pdd_header,
    }

    for label, build in builders.items():
        seen.clear()
        monkeypatch.setattr(settings, "x402_pay_to_address", "0x" + "a" * 40)
        build()
        monkeypatch.setattr(settings, "x402_pay_to_address", "0x" + "b" * 40)
        build()
        assert len(seen) == 2, f"{label} did not route through the challenge cache"
        assert seen[0] != seen[1], (
            f"{label}: changing pay_to did not bust the challenge cache — a "
            "cashier change would keep settling to the old address"
        )


def _city_gate_header(mod):  # noqa: ANN001, ANN202 - test helper
    from app.city_compliance import gate

    return gate.build_payment_required_header(
        mod.SPEC,
        input_example={"address": mod.SPEC.sample_address},
        output_example=mod.discovery_output_example(),
    )


def _mn_header() -> str:
    from app import mn_compliance

    return mn_compliance.build_payment_required_header()


def _tx_header() -> str:
    from app import tx_decision

    return tx_decision.build_payment_required_header()


def _diligence_header() -> str:
    from app import diligence_pack

    return diligence_pack.build_payment_required_header()


def _pdd_header() -> str:
    from app import property_due_diligence_agent

    return property_due_diligence_agent.build_payment_required_header()


def test_the_same_inputs_are_stable_across_calls() -> None:
    """A fingerprint that churned would rebuild against the flaky facilitator
    on every request, which is the whole thing this cache prevents."""
    from app import challenge_cache

    args = dict(network="eip155:8453", price="$0.01", description="d",
                input_example={"k": [1, 2]}, output_example={"z": None})
    assert challenge_cache.fingerprint(**args) == challenge_cache.fingerprint(**args)
