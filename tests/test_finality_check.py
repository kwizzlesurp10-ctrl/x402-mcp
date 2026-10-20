"""app/finality_check.py — classification against real Base RPC safety tags.

RPC responses are mocked (no live network calls in unit tests); the
classification boundaries themselves are what's under test.
"""

from __future__ import annotations

import pytest

from app import finality_check

SAFE_BLOCK = 100
FINALIZED_BLOCK = 90
LATEST_BLOCK = 110


def _block(number: int) -> dict:
    return {"number": hex(number)}


async def _fake_rpc(client, method, params):
    if method == "eth_getBlockByNumber":
        tag = params[0]
        return {
            "safe": _block(SAFE_BLOCK),
            "finalized": _block(FINALIZED_BLOCK),
            "latest": _block(LATEST_BLOCK),
        }[tag]
    raise AssertionError(f"unexpected RPC method in this fixture: {method}")


def _patch_rpc(monkeypatch, tx_result):
    async def rpc(client, method, params):
        if method == "eth_getTransactionByHash":
            return tx_result
        return await _fake_rpc(client, method, params)

    monkeypatch.setattr(finality_check, "_rpc", rpc)


@pytest.mark.asyncio
async def test_not_found(monkeypatch) -> None:
    _patch_rpc(monkeypatch, None)
    result = await finality_check.check_finality("0x" + "a" * 64)
    assert result["status"] == "not_found"
    assert result["included"] is False
    assert result["tx_block"] is None


@pytest.mark.asyncio
async def test_pending(monkeypatch) -> None:
    _patch_rpc(monkeypatch, {"blockNumber": None})
    result = await finality_check.check_finality("0x" + "a" * 64)
    assert result["status"] == "pending"
    assert result["included"] is False


@pytest.mark.asyncio
async def test_finalized_at_or_behind_finalized_block(monkeypatch) -> None:
    _patch_rpc(monkeypatch, {"blockNumber": hex(FINALIZED_BLOCK - 1)})
    result = await finality_check.check_finality("0x" + "a" * 64)
    assert result["status"] == "finalized"
    assert result["included"] is True
    assert result["confirmations"] == LATEST_BLOCK - (FINALIZED_BLOCK - 1) + 1


@pytest.mark.asyncio
async def test_safe_between_finalized_and_safe_block(monkeypatch) -> None:
    _patch_rpc(monkeypatch, {"blockNumber": hex(FINALIZED_BLOCK + 1)})
    result = await finality_check.check_finality("0x" + "a" * 64)
    assert result["status"] == "safe"


@pytest.mark.asyncio
async def test_unsafe_ahead_of_safe_block(monkeypatch) -> None:
    _patch_rpc(monkeypatch, {"blockNumber": hex(SAFE_BLOCK + 1)})
    result = await finality_check.check_finality("0x" + "a" * 64)
    assert result["status"] == "unsafe"


@pytest.mark.asyncio
async def test_boundary_exactly_at_safe_block_is_safe_not_unsafe(monkeypatch) -> None:
    _patch_rpc(monkeypatch, {"blockNumber": hex(SAFE_BLOCK)})
    result = await finality_check.check_finality("0x" + "a" * 64)
    assert result["status"] == "safe"


@pytest.mark.asyncio
async def test_boundary_exactly_at_finalized_block_is_finalized(monkeypatch) -> None:
    _patch_rpc(monkeypatch, {"blockNumber": hex(FINALIZED_BLOCK)})
    result = await finality_check.check_finality("0x" + "a" * 64)
    assert result["status"] == "finalized"


@pytest.mark.asyncio
async def test_response_always_includes_the_reference_blocks(monkeypatch) -> None:
    _patch_rpc(monkeypatch, {"blockNumber": hex(SAFE_BLOCK + 1)})
    result = await finality_check.check_finality("0x" + "a" * 64)
    assert result["safe_block"] == SAFE_BLOCK
    assert result["finalized_block"] == FINALIZED_BLOCK
    assert result["latest_block"] == LATEST_BLOCK
    assert "why" in result and result["why"]
