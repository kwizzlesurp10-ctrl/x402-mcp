"""Verified-revenue classification: fake/test/testnet/self rows never count."""

from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app import ledger_quality, ledger_store
from app.config import settings
from app.ledger_store import RedisLedgerStore
from app.main import app, invalidate_ledger_cache
from app.swarm import ledger_writer

H = "0x" + "a1" * 32
H2 = "0x" + "b2" * 32
H3 = "0x" + "c3" * 32
STRANGER = "0x7e571e959cc7c75ccdd2eac24f8775ea2eaa2f09"
OPERATOR = "0x67ffc9b439ae24b0f7c7ca837c4adfafa06f9d38"


def _row(tx, *, network="eip155:8453", payer=STRANGER, amount=0.01, ts="2026-10-01T00:00:00+00:00", settled=True):
    return {"ts": ts, "kind": "revenue", "network": network, "amount_usdc": amount, "tx": tx,
            "settled": settled, "product_id": "p", "payer": payer}


@pytest.fixture
def mainnet(monkeypatch):
    monkeypatch.setattr(settings, "x402_default_network", "eip155:8453")


def test_classification_covers_every_bucket(mainnet) -> None:
    rows = [
        _row(H),                                   # verified
        _row(H, ts="2026-10-02T00:00:00+00:00"),   # duplicate of the first
        _row("0xdeadbeef"),                        # fake id
        _row(None),                                # missing id
        _row("0xcatalog0"),                        # catalog placeholder
        _row(H2, network="eip155:84532"),          # Sepolia
        _row("0xabc", network="eip155:84532"),     # Sepolia fixture → testnet first
        _row(H3, network="eip155:8453,solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"),
        _row("0x" + "d4" * 32, payer=OPERATOR),    # self-payment via OPERATOR_WALLETS
        _row("0x" + "e5" * 32, payer="0x0d25A44f74868eCE53B305C97139CF4B62963410"),  # payTo paying itself
        _row("0x" + "f6" * 32, payer=None),        # unknown
        _row("0x" + "07" * 32, settled=False),
        _row("0x" + "18" * 32),                    # excluded by audit
    ]
    out = ledger_quality.annotate_revenue_rows(
        rows, operator_wallets={OPERATOR}, exclusions={"0x" + "18" * 32: "no transfer"}
    )
    labels = [r["ledger_quality"] for r in out]
    assert labels == [
        "verified_external", "duplicate", "test_tx", "test_tx", "test_tx", "testnet", "testnet",
        "network_unverified", "self_payment", "self_payment", "unknown_payer", "unsettled", "excluded",
    ]
    assert [r["counts_as_revenue"] for r in out].count(True) == 1
    summary = ledger_quality.summarize(out)
    assert summary["raw"]["rows"] == 13
    assert summary["verified_external"] == {"rows": 1, "usdc": 0.01}
    assert summary["excluded"]["rows"] == 12
    # raw input untouched
    assert "ledger_quality" not in rows[0]


def test_duplicate_detection_keeps_the_oldest(mainnet) -> None:
    newest_first = [_row(H, ts="2026-10-03T00:00:00+00:00"), _row(H, ts="2026-10-01T00:00:00+00:00")]
    out = ledger_quality.annotate_revenue_rows(newest_first, operator_wallets={OPERATOR}, exclusions={})
    assert [r["ledger_quality"] for r in out] == ["duplicate", "verified_external"]


def test_production_store_refuses_fake_and_testnet_rows(mainnet, monkeypatch) -> None:
    store = RedisLedgerStore(fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(ledger_store, "ledger_store", store)
    bad = ledger_writer.record_revenue(agent_id="a", amount_usdc=0.01, network="eip155:8453", product_id="p", tx="0xdeadbeef")
    assert "rejected" in bad
    bad2 = ledger_writer.record_revenue(agent_id="a", amount_usdc=0.01, network="eip155:84532", product_id="p", tx=H)
    assert "rejected" in bad2
    good = ledger_writer.record_revenue(agent_id="a", amount_usdc=0.01, network="eip155:8453", product_id="p", tx=H, payer=STRANGER)
    assert "rejected" not in good
    rows = store.read("revenue", None)
    assert [r["tx"] for r in rows] == [H]


def test_file_ledger_stays_permissive_for_dev(monkeypatch, tmp_path) -> None:
    from app import ledger_io

    monkeypatch.setattr(ledger_store, "ledger_store", None)
    monkeypatch.setattr(ledger_io, "LEDGER", tmp_path)
    row = ledger_writer.record_revenue(agent_id="a", amount_usdc=0.01, network="eip155:84532", product_id="p", tx="0xabc")
    assert "rejected" not in row


def test_revenue_endpoint_and_summary(mainnet, monkeypatch) -> None:
    store = RedisLedgerStore(fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(ledger_store, "ledger_store", store)
    monkeypatch.setattr(settings, "operator_wallets", OPERATOR)
    # Seed legacy bad rows directly (as history already contains them).
    import json

    for r in (_row(H), _row("0xabc"), _row(H2, network="eip155:84532"), _row("0x" + "d4" * 32, payer=OPERATOR)):
        store._client.rpush("ledger:revenue", json.dumps(r))
    invalidate_ledger_cache()
    client = TestClient(app)
    rows = client.get("/ledger/revenue").json()
    assert sum(1 for r in rows if r["counts_as_revenue"]) == 1
    assert {r["ledger_quality"] for r in rows} == {"verified_external", "test_tx", "testnet", "self_payment"}
    summary = client.get("/ledger-summary/revenue").json()
    assert summary["raw"]["rows"] == 4
    assert summary["verified_external"]["rows"] == 1
    # nothing was deleted
    assert store._client.llen("ledger:revenue") == 4


def test_committed_exclusions_parse() -> None:
    excl = ledger_quality.load_exclusions()
    assert excl, "app/revenue_exclusions.json should list the audited no-transfer txs"
    assert all(ledger_quality.is_tx_hash(tx) for tx in excl)
