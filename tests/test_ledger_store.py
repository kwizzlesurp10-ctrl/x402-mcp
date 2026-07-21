"""Redis-backed ledgers — settled sales survive a restart on a diskless host.

Uses fakeredis; no live Redis server is required (or allowed) on this host.
"""

from __future__ import annotations

import fakeredis
import pytest

from app import ledger_io, ledger_store
from app.ledger_store import RedisLedgerStore, build_ledger_store
from app.swarm import ledger_writer


@pytest.fixture
def redis_ledger(monkeypatch) -> RedisLedgerStore:
    """Point both the reader and the writer at a fake Redis."""
    store = RedisLedgerStore(fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(ledger_store, "ledger_store", store)
    return store


def test_written_rows_read_back_newest_first(redis_ledger) -> None:
    ledger_writer.record_spend(
        agent_id="a1",
        amount_usdc=0.01,
        network="eip155:8453",
        url="https://upstream.test/search",
        run_id="run-1",
        tx="0xspend",
        settled=True,
    )
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.25,
        network="eip155:8453",
        product_id="p1",
        tx="0xrevenue",
    )

    spend = ledger_io.read_ledger_rows("spend")
    revenue = ledger_io.read_ledger_rows("revenue")

    assert [r["tx"] for r in spend] == ["0xspend"]
    assert [r["tx"] for r in revenue] == ["0xrevenue"]
    # Atomic amounts are what the dashboard nets on.
    assert revenue[0]["amount_usdc_atomic"] == 250_000
    # The ledgers stay separate lists.
    assert revenue[0]["kind"] == "revenue"


def test_ordering_is_newest_first(redis_ledger) -> None:
    for i in range(3):
        ledger_writer.record_revenue(
            agent_id="seller",
            amount_usdc=0.25,
            network="eip155:8453",
            product_id=f"p{i}",
        )

    rows = ledger_io.read_ledger_rows("revenue")

    assert [r["product_id"] for r in rows] == ["p2", "p1", "p0"]


def test_limit_none_reads_everything(redis_ledger) -> None:
    """Aggregation passes limit=None and must not be truncated."""
    for i in range(5):
        ledger_writer.record_revenue(
            agent_id="seller",
            amount_usdc=0.10,
            network="eip155:8453",
            product_id=f"p{i}",
        )

    assert len(ledger_io.read_ledger_rows("revenue", limit=None)) == 5
    assert len(ledger_io.read_ledger_rows("revenue", limit=2)) == 2


def test_rows_survive_a_new_store_over_the_same_redis(monkeypatch) -> None:
    """The whole point: a restart rebuilds the store, the sale record stays."""
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(ledger_store, "ledger_store", RedisLedgerStore(client))
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.25,
        network="eip155:8453",
        product_id="p1",
        tx="0xsurvivor",
    )

    # A fresh process: new store object, same Redis.
    monkeypatch.setattr(ledger_store, "ledger_store", RedisLedgerStore(client))

    rows = ledger_io.read_ledger_rows("revenue")
    assert [r["tx"] for r in rows] == ["0xsurvivor"]


def test_a_corrupt_row_does_not_sink_the_ledger(redis_ledger) -> None:
    ledger_writer.record_revenue(
        agent_id="seller",
        amount_usdc=0.25,
        network="eip155:8453",
        product_id="good",
    )
    redis_ledger._client.rpush("ledger:revenue", "{not json")

    rows = ledger_io.read_ledger_rows("revenue")

    assert [r["product_id"] for r in rows] == ["good"]


def test_trims_to_the_row_cap(redis_ledger, monkeypatch) -> None:
    monkeypatch.setattr(ledger_store, "MAX_ROWS", 3)
    for i in range(5):
        ledger_writer.record_revenue(
            agent_id="seller",
            amount_usdc=0.10,
            network="eip155:8453",
            product_id=f"p{i}",
        )

    rows = ledger_io.read_ledger_rows("revenue")

    # Oldest rows are dropped; the most recent survive.
    assert [r["product_id"] for r in rows] == ["p4", "p3", "p2"]


def test_bad_ledger_name_is_rejected(redis_ledger) -> None:
    with pytest.raises(ValueError):
        redis_ledger.read("payroll", None)
    with pytest.raises(ValueError):
        redis_ledger.append("payroll", {})


def test_files_stay_the_default_without_redis_url(monkeypatch) -> None:
    monkeypatch.setattr(ledger_store.settings, "redis_url", "")

    assert build_ledger_store() is None


def test_unreachable_redis_falls_back_to_files(monkeypatch) -> None:
    """A dead Redis degrades the ledger; it must never stop the server booting."""
    monkeypatch.setattr(ledger_store.settings, "redis_url", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(ledger_store, "fallback_reason", None)

    assert build_ledger_store() is None
    assert ledger_store.fallback_reason  # /doctor fails on this
