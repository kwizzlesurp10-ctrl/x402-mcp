"""Autonomous Cache Warmer & Pulse Auto-Freshness Engine.

Runs as a background task within the FastAPI lifespan. Periodically:
1. Pre-computes Base Network Pulse telemetry via app.pulse.get_pulse()
   to ensure zero cold-start latency for /pulse, /base/tx-decision, and MCP tools.
2. Pre-warms city compliance sample addresses across the 14 supported US cities
   in app.city_compliance, keeping in-memory cache fresh for instant diligence lookups.
3. Maintains telemetry stats (cycles, duration, timestamps, errors).
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
import logging
import time
from typing import Any

from app.config import settings

logger = logging.getLogger("x402.cache_warmer")


class CacheWarmer:
    """Background engine that proactively refreshes high-demand caches."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False
        self._latest_pulse: dict[str, Any] | None = None
        self._latest_pulse_time: float | None = None
        self._cycle_count: int = 0
        self._error_count: int = 0
        self._last_run_iso: str | None = None
        self._last_duration_ms: float = 0.0
        self._last_errors: list[str] = []

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def get_latest_pulse(self) -> dict[str, Any] | None:
        """Return the most recently pre-warmed Base Pulse report, if any."""
        return self._latest_pulse

    def get_stats(self) -> dict[str, Any]:
        """Telemetry snapshot of the cache warmer engine."""
        return {
            "enabled": getattr(settings, "cache_warmer_enabled", True),
            "interval_seconds": getattr(settings, "cache_warmer_interval_seconds", 60),
            "running": self.is_running,
            "cycle_count": self._cycle_count,
            "error_count": self._error_count,
            "last_run": self._last_run_iso,
            "last_duration_ms": round(self._last_duration_ms, 2),
            "pulse_available": self._latest_pulse is not None,
            "recent_errors": list(self._last_errors[-5:]),
        }

    async def warm_pulse(self) -> bool:
        """Refresh Base Network Pulse intelligence."""
        try:
            from app import pulse

            report = await asyncio.wait_for(pulse.get_pulse(), timeout=20.0)
            self._latest_pulse = report
            self._latest_pulse_time = time.monotonic()
            logger.debug("Cache warmer: Base pulse refreshed at block %s", report.get("latest_block"))
            return True
        except Exception as exc:
            msg = f"Pulse warm error: {exc}"
            logger.debug(msg)
            self._last_errors.append(msg)
            self._error_count += 1
            return False

    async def warm_cities(self) -> int:
        """Pre-warm sample addresses across registered US city compliance modules."""
        try:
            from app.city_compliance import registry

            cities = list(registry.CITIES.values())
        except Exception as exc:
            msg = f"City registry load error: {exc}"
            logger.debug(msg)
            self._last_errors.append(msg)
            self._error_count += 1
            return 0

        warmed = 0
        for mod in cities:
            spec = getattr(mod, "SPEC", None)
            if not spec or not getattr(spec, "sample_address", None):
                continue
            try:
                # Query the sample address with a short timeout to warm module cache
                await asyncio.wait_for(mod.check_property(spec.sample_address), timeout=5.0)
                warmed += 1
            except Exception as exc:
                # Soft failure: municipal open-data endpoints can be flaky or rate-limited
                logger.debug("City sample pre-warm error for %s: %s", spec.code, exc)
            # Gentle yield between cities to prevent blocking
            await asyncio.sleep(0.05)

        logger.debug("Cache warmer: %d/%d city samples refreshed", warmed, len(cities))
        return warmed

    async def warm_cycle(self) -> dict[str, Any]:
        """Execute a single warming cycle and update metrics."""
        start = time.monotonic()
        pulse_ok = await self.warm_pulse()
        cities_warmed = await self.warm_cities()
        duration = (time.monotonic() - start) * 1000

        self._cycle_count += 1
        self._last_run_iso = datetime.now(UTC).isoformat()
        self._last_duration_ms = duration

        return {
            "cycle": self._cycle_count,
            "duration_ms": round(duration, 2),
            "pulse_ok": pulse_ok,
            "cities_warmed": cities_warmed,
            "timestamp": self._last_run_iso,
        }

    async def run_loop(self) -> None:
        """Continuous background execution loop."""
        self._running = True
        interval = getattr(settings, "cache_warmer_interval_seconds", 60)
        logger.info("Autonomous cache warmer loop started (interval=%ds)", interval)
        try:
            initial_delay = getattr(settings, "cache_warmer_initial_delay_seconds", 5.0)
            if initial_delay > 0:
                await asyncio.sleep(initial_delay)
            while self._running:
                try:
                    await self.warm_cycle()
                except Exception as exc:
                    self._error_count += 1
                    msg = f"Unexpected cycle error: {exc}"
                    logger.warning(msg)
                    self._last_errors.append(msg)

                # Wait for next interval or cancellation
                interval = getattr(settings, "cache_warmer_interval_seconds", 60)
                await asyncio.sleep(max(5, interval))
        except asyncio.CancelledError:
            logger.info("Autonomous cache warmer task cancelled")
            raise
        finally:
            self._running = False

    def start(self) -> asyncio.Task[None] | None:
        """Start the background task if enabled and not already running."""
        if not getattr(settings, "cache_warmer_enabled", True):
            logger.info("Cache warmer is disabled by configuration")
            return None
        self._running = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run_loop())
        return self._task

    async def stop(self) -> None:
        """Stop the background task gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None


# Global singleton instance
cache_warmer = CacheWarmer()
