"""Tests for sale-watch Base RPC helpers."""

from __future__ import annotations

import json
import os
import urllib.error
from unittest.mock import patch

import pytest

from scripts.sale_watch_base import (
    RpcClientError,
    RpcInfrastructureError,
    fetch_transfer_logs,
    pay_to_transfer_topic,
    rpc_call,
    rpc_endpoint_urls,
)


def test_rpc_endpoint_urls_prefers_base_rpc_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASE_RPC_URL", "https://custom-rpc.example")
    monkeypatch.setenv("RPC", "https://legacy.example")
    urls = rpc_endpoint_urls()
    assert urls[0] == "https://custom-rpc.example"
    assert "https://legacy.example" in urls
    assert "https://mainnet.base.org" in urls


def test_pay_to_transfer_topic() -> None:
    pay_to = "0x05e1720bB82F86B5bc7940a99FDC702E32256357"
    topic = pay_to_transfer_topic(pay_to)
    assert topic.endswith(pay_to[2:].lower())
    assert len(topic) == 66


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_rpc_call_rotates_on_retryable_failure() -> None:
    responses: list[object] = [
        urllib.error.HTTPError("https://a", 429, "Too Many Requests", {}, None),
        _FakeHttpResponse({"jsonrpc": "2.0", "id": 1, "result": "0x10"}),
    ]

    def fake_urlopen(req, timeout=45):
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    with patch("scripts.sale_watch_base.time.sleep"), patch(
        "urllib.request.urlopen", side_effect=fake_urlopen
    ):
        assert rpc_call("eth_blockNumber", [], endpoints=["https://a", "https://b"]) == "0x10"


def test_rpc_call_raises_infrastructure_when_all_fail() -> None:
    def always_429(req, timeout=45):
        raise urllib.error.HTTPError("https://a", 429, "Too Many Requests", {}, None)

    with patch("scripts.sale_watch_base.time.sleep"), patch(
        "urllib.request.urlopen", side_effect=always_429
    ):
        with pytest.raises(RpcInfrastructureError):
            rpc_call("eth_blockNumber", [], endpoints=["https://only.example"])


def test_fetch_transfer_logs_chunks_range() -> None:
    calls: list[tuple[int, int]] = []

    def fake_rpc(method, params):
        assert method == "eth_getLogs"
        filt = params[0]
        from_b = int(filt["fromBlock"], 16)
        to_b = int(filt["toBlock"], 16)
        calls.append((from_b, to_b))
        return []

    fetch_transfer_logs(
        fake_rpc,
        usdc="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        pay_to="0x05e1720bB82F86B5bc7940a99FDC702E32256357",
        start_block=0,
        end_block=2000,
        chunk_size=900,
    )
    assert calls == [(0, 899), (900, 1799), (1800, 2000)]


def test_rpc_call_non_retryable_raises_client_error() -> None:
    def bad_request(req, timeout=45):
        raise urllib.error.HTTPError("https://a", 400, "Bad Request", {}, None)

    with patch("urllib.request.urlopen", side_effect=bad_request):
        with pytest.raises(RpcClientError):
            rpc_call("eth_blockNumber", [], endpoints=["https://a"])


def test_live_eth_block_number() -> None:
    if os.environ.get("RUN_LIVE_RPC") != "1":
        pytest.skip("set RUN_LIVE_RPC=1 to hit public Base RPC")
    result = rpc_call("eth_blockNumber", [])
    assert isinstance(result, str) and result.startswith("0x")
    assert int(result, 16) > 0
