"""Tests for Autonomous Cache Warmer & Pulse Auto-Freshness Engine."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from app.cache_warmer import CacheWarmer, cache_warmer
from app.config import settings


@pytest.mark.asyncio
async def test_cache_warmer_stats_structure() -> None:
    warmer = CacheWarmer()
    stats = warmer.get_stats()
    assert "enabled" in stats
    assert "interval_seconds" in stats
    assert "running" in stats
    assert "cycle_count" in stats
    assert stats["cycle_count"] == 0
    assert stats["pulse_available"] is False


@pytest.mark.asyncio
async def test_cache_warmer_warm_pulse_success() -> None:
    warmer = CacheWarmer()
    mock_report = {
        "latest_block": 20491820,
        "eth_price_usd": 3200.50,
        "assessment": {"verdict": "SETTLE_NOW"},
    }
    with patch("app.pulse.get_pulse", new_callable=AsyncMock) as mock_get_pulse:
        mock_get_pulse.return_value = mock_report
        success = await warmer.warm_pulse()
        assert success is True
        assert warmer.get_latest_pulse() == mock_report
        stats = warmer.get_stats()
        assert stats["pulse_available"] is True


@pytest.mark.asyncio
async def test_cache_warmer_warm_pulse_error_handling() -> None:
    warmer = CacheWarmer()
    with patch("app.pulse.get_pulse", side_effect=RuntimeError("RPC timeout")):
        success = await warmer.warm_pulse()
        assert success is False
        assert warmer.get_latest_pulse() is None
        stats = warmer.get_stats()
        assert stats["error_count"] >= 1
        assert any("RPC timeout" in e for e in stats["recent_errors"])


@pytest.mark.asyncio
async def test_cache_warmer_warm_cities_resilience() -> None:
    warmer = CacheWarmer()
    from unittest.mock import MagicMock
    mock_mod = MagicMock()
    mock_mod.SPEC.sample_address = "123 Main St"
    mock_mod.SPEC.code = "mock"
    mock_mod.check_property = AsyncMock(return_value={"status": "ok"})
    with patch("app.city_compliance.registry.CITIES", {"mock": mock_mod}):
        warmed = await warmer.warm_cities()
        assert warmed == 1


@pytest.mark.asyncio
async def test_cache_warmer_warm_cycle() -> None:
    warmer = CacheWarmer()
    from unittest.mock import MagicMock
    mock_mod = MagicMock()
    mock_mod.SPEC.sample_address = "123 Main St"
    mock_mod.SPEC.code = "mock"
    mock_mod.check_property = AsyncMock(return_value={"status": "ok"})
    with (
        patch("app.pulse.get_pulse", new_callable=AsyncMock) as mock_get_pulse,
        patch("app.city_compliance.registry.CITIES", {"mock": mock_mod}),
    ):
        mock_get_pulse.return_value = {"latest_block": 100}
        res = await warmer.warm_cycle()
        assert res["cycle"] == 1
        assert res["duration_ms"] >= 0
        assert res["pulse_ok"] is True
        assert res["cities_warmed"] == 1
        assert "timestamp" in res

        stats = warmer.get_stats()
        assert stats["cycle_count"] == 1
        assert stats["last_run"] is not None


@pytest.mark.asyncio
async def test_cache_warmer_start_and_stop() -> None:
    warmer = CacheWarmer()
    task = warmer.start()
    assert task is not None
    assert warmer.is_running is True

    await asyncio.sleep(0.01)
    await warmer.stop()
    assert warmer.is_running is False
    assert warmer._task is None
