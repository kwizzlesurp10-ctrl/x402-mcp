from __future__ import annotations

import pytest

from scripts.sale_watch import RpcHttpError, classify_strangers, fetch_logs_chunked


def _log(frm: str, tx: str, block: int, amt_raw: str = hex(250_000)) -> dict:
    return {
        "topics": [
            "0xddf252ad",
            "0x" + "0" * 24 + frm[2:],
            "0x" + "0" * 24 + "aa",
        ],
        "data": amt_raw,
        "transactionHash": tx,
        "blockNumber": hex(block),
    }


def test_chunked_logs_split_on_413() -> None:
    calls: list[tuple[int, int]] = []

    def rpc_fn(method, params):
        assert method == "eth_getLogs"
        filt = params[0]
        start = int(filt["fromBlock"], 16)
        end = int(filt["toBlock"], 16)
        calls.append((start, end))
        if end - start + 1 > 200:
            raise RpcHttpError(413, "Payload Too Large")
        return [_log("0x" + "1" * 40, f"0x{start:064x}", start)]

    logs = fetch_logs_chunked(
        rpc_fn,
        usdc="0x8335",
        topic_to="0x" + "0" * 64,
        start=1000,
        latest=1599,
        chunk=500,
    )
    assert logs
    oversized = [(s, e) for s, e in calls if e - s + 1 > 200]
    fitted = [(s, e) for s, e in calls if e - s + 1 <= 200]
    assert oversized, "should attempt a too-large window first"
    assert fitted
    assert min(s for s, _ in fitted) == 1000
    assert max(e for _, e in fitted) == 1599


def test_classify_skips_our_wallets() -> None:
    ours = {"0x67ffc9b439ae24b0f7c7ca837c4adfafa06f9d38"}
    logs = [
        _log("0x67ffc9b439ae24b0f7c7ca837c4adfafa06f9d38", "0xaaa", 1),
        _log("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "0xbbb", 2),
    ]
    strangers = classify_strangers(logs, ours)
    assert len(strangers) == 1
    assert strangers[0][2] == "0xbbb"


def test_413_on_single_block_still_raises() -> None:
    def rpc_fn(method, params):
        raise RpcHttpError(413, "Payload Too Large")

    with pytest.raises(RpcHttpError):
        fetch_logs_chunked(
            rpc_fn,
            usdc="0x8335",
            topic_to="0x" + "0" * 64,
            start=10,
            latest=10,
            chunk=50,
        )
