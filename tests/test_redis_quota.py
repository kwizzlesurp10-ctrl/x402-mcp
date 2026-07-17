"""RedisQuotaStore: store selection, restart persistence, doctor truthfulness.

Uses fakeredis — no live Redis server is required (or allowed) on this host.
"""

from __future__ import annotations

import fakeredis
import pytest

from app import commerce, doctor
from app.commerce import InMemoryQuotaStore, RedisQuotaStore, build_quota_store
from app.config import settings


@pytest.fixture
def fake_server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


def _fake_client(server: fakeredis.FakeServer) -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(server=server, decode_responses=True)


@pytest.fixture
def offline_doctor(monkeypatch: pytest.MonkeyPatch):
    """Doctor with network probes stubbed — these tests only assert the redis check."""
    monkeypatch.setattr(doctor, "_ping_url", lambda url, **kw: (True, "HTTP 200"))
    return doctor


def _redis_check(report: dict) -> dict:
    return next(c for c in report["checks"] if c["id"] == "redis")


# -- store selection truth table ---------------------------------------------


def test_env_unset_selects_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "redis_url", None)
    store = build_quota_store()
    assert type(store) is InMemoryQuotaStore
    assert store.mode == "memory"
    assert store.fallback_reason is None


def test_reachable_redis_selects_redis_store(
    monkeypatch: pytest.MonkeyPatch, fake_server: fakeredis.FakeServer
) -> None:
    import redis

    monkeypatch.setattr(settings, "redis_url", "redis://fake-host:6379/0")
    monkeypatch.setattr(
        redis.Redis,
        "from_url",
        classmethod(lambda cls, url, **kw: _fake_client(fake_server)),
    )
    store = build_quota_store()
    assert isinstance(store, RedisQuotaStore)
    assert store.mode == "redis"
    assert store.ping() is True


def test_unreachable_redis_falls_back_to_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Nothing listens on port 1; connect fails fast and must NOT raise.
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    store = build_quota_store()
    assert type(store) is InMemoryQuotaStore
    assert store.mode == "memory"
    assert store.fallback_reason  # recorded so /doctor can FAIL truthfully


# -- restart persistence (the pay-then-lose-entitlement bug) -------------------


def test_entitlements_survive_restart(fake_server: fakeredis.FakeServer) -> None:
    store1 = RedisQuotaStore(_fake_client(fake_server))
    store1.activate_pro_tier("buyer-1")
    store1.add_credits("buyer-1", 25)
    store1.consume_quota("buyer-1")
    store1.consume_quota("buyer-1")

    # Simulated process restart: fresh store instance, same Redis data.
    store2 = RedisQuotaStore(_fake_client(fake_server))
    assert store2.get_tier("buyer-1") == "pro"
    assert store2.get_credits("buyer-1") == 25
    snap = store2.peek("buyer-1")
    assert snap.tier == "pro"
    assert snap.calls_this_month == 2
    assert snap.quota_remaining == settings.pro_tier_monthly_quota - 2


def test_memory_store_loses_entitlements_on_restart() -> None:
    """The contrast case: exactly why RedisQuotaStore exists."""
    store1 = InMemoryQuotaStore()
    store1.activate_pro_tier("buyer-1")
    store1.add_credits("buyer-1", 25)

    store2 = InMemoryQuotaStore()
    assert store2.get_tier("buyer-1") == "free"
    assert store2.get_credits("buyer-1") == 0


def test_stripe_idempotency_survives_restart(
    fake_server: fakeredis.FakeServer,
) -> None:
    store1 = RedisQuotaStore(_fake_client(fake_server))
    first = store1.fulfill_stripe_credits("buyer-2", 100, "evt_123")
    assert first["credits_added"] == 100

    store2 = RedisQuotaStore(_fake_client(fake_server))
    replay = store2.fulfill_stripe_credits("buyer-2", 100, "evt_123")
    assert replay["already_fulfilled"] is True
    assert store2.get_credits("buyer-2") == 100  # not double-credited


def test_stripe_pro_fulfillment_idempotent_on_redis(
    fake_server: fakeredis.FakeServer,
) -> None:
    store = RedisQuotaStore(_fake_client(fake_server))
    first = store.fulfill_stripe_pro_tier("buyer-3", "evt_pro_1")
    assert first["activated"] is True
    replay = store.fulfill_stripe_pro_tier("buyer-3", "evt_pro_1")
    assert replay["already_fulfilled"] is True
    assert store.get_tier("buyer-3") == "pro"


def test_snapshot_reports_actual_redis_mode(
    fake_server: fakeredis.FakeServer,
) -> None:
    store = RedisQuotaStore(_fake_client(fake_server))
    store.consume_quota("snap-redis-agent")
    snap = store.snapshot()
    assert snap["config"]["redis_mode"] == "redis"
    agent = next(
        a for a in snap["agents"] if a["agent_id"] == "snap-redis-agent"
    )
    assert agent["calls_this_month"] == 1


# -- /doctor reports the ACTUAL store mode, not the env var --------------------


def test_doctor_passes_on_live_redis_store(
    monkeypatch: pytest.MonkeyPatch,
    fake_server: fakeredis.FakeServer,
    offline_doctor,
) -> None:
    store = RedisQuotaStore(_fake_client(fake_server))
    monkeypatch.setattr(commerce, "quota_store", store)
    report = offline_doctor.run_checks()
    check = _redis_check(report)
    assert check["status"] == "pass"
    assert report["config"]["redis_mode"] == "redis"


def test_doctor_fails_when_env_set_but_store_fell_back(
    monkeypatch: pytest.MonkeyPatch, offline_doctor
) -> None:
    fallback = InMemoryQuotaStore()
    fallback.fallback_reason = "ConnectionError: connection refused"
    monkeypatch.setattr(commerce, "quota_store", fallback)
    monkeypatch.setattr(settings, "redis_url", "redis://down-host:6379/0")
    report = offline_doctor.run_checks()
    check = _redis_check(report)
    assert check["status"] == "fail"
    assert "IN-MEMORY" in check["message"]
    assert report["config"]["redis_mode"] == "memory"


def test_doctor_warns_when_env_unset_and_memory(
    monkeypatch: pytest.MonkeyPatch, offline_doctor
) -> None:
    monkeypatch.setattr(commerce, "quota_store", InMemoryQuotaStore())
    monkeypatch.setattr(settings, "redis_url", None)
    report = offline_doctor.run_checks()
    check = _redis_check(report)
    assert check["status"] == "warn"
    assert report["config"]["redis_mode"] == "memory"


def test_doctor_fails_when_redis_store_loses_connection(
    monkeypatch: pytest.MonkeyPatch,
    fake_server: fakeredis.FakeServer,
    offline_doctor,
) -> None:
    store = RedisQuotaStore(_fake_client(fake_server))

    def dead_ping() -> bool:
        raise ConnectionError("connection lost")

    monkeypatch.setattr(store, "ping", dead_ping)
    monkeypatch.setattr(commerce, "quota_store", store)
    report = offline_doctor.run_checks()
    assert _redis_check(report)["status"] == "fail"
