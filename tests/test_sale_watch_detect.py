"""sale-watch must notice external ledger rows the Nov 15–16 burst missed on-chain."""

from __future__ import annotations

from scripts.alerts import event_key
from datetime import datetime, timedelta, timezone

from scripts.sale_watch_detect import (
    external_sales_from_ledger_rows,
    merge_stranger_payments,
    normalize_wallet,
    strangers_from_transfer_logs,
)

OPERATOR = normalize_wallet("0x67ffc9B439aE24B0f7C7cA837C4AdfAFA06F9d38")
NOV_15_16_LEDGER_FIXTURE: list[dict] = [
    {
        "ts": "2026-11-16T03:22:02.953192+00:00",
        "settled": True,
        "is_operator_settle": False,
        "payer": "0x79f896ff38691931fc2494610c106ad755e6f758",
        "tx": "0xd83d4696e5ffadbb85e97173d13b7596690cddd57795724a084dfc0232ebcaa5",
        "amount_usdc": 0.01,
        "product_id": "mn-property-check",
    },
    {
        "ts": "2026-11-16T09:45:22.859500+00:00",
        "settled": True,
        "is_operator_settle": False,
        "payer": "0x82cef1cdc34d65cf690235dc24e823a6585a6f86",
        "tx": "0xe5de642092be85a08aa1278d890a465c5afea8c6f29b861479cd851a9b465f32",
        "amount_usdc": 0.01,
        "product_id": "property-due-diligence-agent",
    },
    {
        "ts": "2026-11-16T04:30:43.590039+00:00",
        "settled": True,
        "is_operator_settle": False,
        "payer": "0x82cef1cdc34d65cf690235dc24e823a6585a6f86",
        "tx": "0xf15661cd17477b9ca51667bc4e8d2fd850e44e2e2e80f0e17b5baf2d4b3cfe23",
        "amount_usdc": 0.01,
        "product_id": "mn-property-check",
    },
]

TRANSFER_LOG = {
    "topics": [
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
        "0x00000000000000000000000082cef1cdc34d65cf690235dc24e823a6585a6f86",
        "0x0000000000000000000000000d25a44f74868ece53b305c97139cf4b62963410",
    ],
    "data": "0x0000000000000000000000000000000000000000000000000000000000002710",
    "transactionHash": "0xe5de642092be85a08aa1278d890a465c5afea8c6f29b861479cd851a9b465f32",
    "blockNumber": "0x376a9e6",
}


def test_nov_15_16_fixture_rows_are_external_sales() -> None:
    ours = {OPERATOR}
    sales = external_sales_from_ledger_rows(NOV_15_16_LEDGER_FIXTURE, ours)
    assert len(sales) == 3
    txs = {s.tx.lower() for s in sales}
    assert "0xd83d4696e5ffadbb85e97173d13b7596690cddd57795724a084dfc0232ebcaa5" in txs
    assert "0xe5de642092be85a08aa1278d890a465c5afea8c6f29b861479cd851a9b465f32" in txs


def test_operator_ledger_rows_are_ignored() -> None:
    rows = [
        {
            "settled": True,
            "is_operator_settle": True,
            "payer": OPERATOR,
            "tx": "0xabc",
            "amount_usdc": 0.01,
        }
    ]
    assert external_sales_from_ledger_rows(rows, {OPERATOR}) == []


def test_merge_prefers_ledger_product_with_chain_block() -> None:
    ours = {OPERATOR}
    chain = strangers_from_transfer_logs([TRANSFER_LOG], ours)
    ledger = external_sales_from_ledger_rows([NOV_15_16_LEDGER_FIXTURE[1]], ours)
    merged = merge_stranger_payments(chain, ledger)
    match = merged[0]
    assert match.product_id == "property-due-diligence-agent"
    assert match.block == int(TRANSFER_LOG["blockNumber"], 16)
    assert match.source == "chain+ledger"
    assert event_key("sale", match.tx)


def test_ledger_lookback_skips_old_rows() -> None:
    ours = {OPERATOR}
    old = {**NOV_15_16_LEDGER_FIXTURE[0], "ts": "2020-01-01T00:00:00+00:00"}
    recent = {
        **NOV_15_16_LEDGER_FIXTURE[0],
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    sales = external_sales_from_ledger_rows(
        [old, recent], ours, lookback=timedelta(hours=1)
    )
    assert len(sales) == 1
    assert sales[0].tx.lower() == recent["tx"].lower()


def test_strangers_from_transfer_logs_skips_operator_wallet() -> None:
    topic_from = "0x000000000000000000000000" + OPERATOR[2:]
    operator_log = {
        **TRANSFER_LOG,
        "topics": [TRANSFER_LOG["topics"][0], topic_from, TRANSFER_LOG["topics"][2]],
        "transactionHash": "0xdead",
    }
    ours = {OPERATOR}
    assert len(strangers_from_transfer_logs([operator_log], ours)) == 0
    assert len(strangers_from_transfer_logs([TRANSFER_LOG], ours)) == 1