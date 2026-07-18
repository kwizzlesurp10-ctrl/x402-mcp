"""Host OS monitoring — real system telemetry for mission control.

Samples CPU, memory, swap, disk, network, and process signals via psutil,
keeps a rolling in-memory history, and synthesizes an ok/warn/critical
verdict so operators (and the dashboard) can see at a glance whether the
box running the swarm is healthy.

Health-level transitions (ok -> warn -> critical and recoveries) are emitted
onto the mission-control SSE stream as `os_alert` events, following the same
fire-and-forget contract as tool events: monitoring must never break the app.
"""

from __future__ import annotations

import asyncio
import os
import platform
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from app.config import settings
from app.ops_events import emit_os_alert

ROOT = Path(__file__).resolve().parents[1]

_LEVELS = ("ok", "warn", "critical")

_history: deque[dict[str, Any]] = deque(maxlen=settings.os_monitor_history_size)
_last_status: str = "ok"
_last_net: tuple[float, int, int] | None = None  # (ts, bytes_sent, bytes_recv)
_self_process = psutil.Process(os.getpid())

# Prime psutil's CPU delta baselines so the first real sample is meaningful
# (cpu_percent with interval=None returns 0.0 on its very first call).
try:
    psutil.cpu_percent(interval=None)
    _self_process.cpu_percent(interval=None)
except Exception:
    pass


def _level(value: float, warn_at: float, crit_at: float) -> str:
    if value >= crit_at:
        return "critical"
    if value >= warn_at:
        return "warn"
    return "ok"


def _verdict(
    cpu_pct: float, mem_pct: float, disk_pct: float
) -> tuple[str, list[str]]:
    """Synthesize an overall health level plus human-readable concerns."""
    checks = (
        ("cpu", cpu_pct, settings.os_cpu_warn_pct, settings.os_cpu_crit_pct),
        ("memory", mem_pct, settings.os_mem_warn_pct, settings.os_mem_crit_pct),
        ("disk", disk_pct, settings.os_disk_warn_pct, settings.os_disk_crit_pct),
    )
    concerns: list[str] = []
    worst = "ok"
    for name, value, warn_at, crit_at in checks:
        level = _level(value, warn_at, crit_at)
        if level != "ok":
            concerns.append(f"{name} at {value:.1f}% ({level})")
        if _LEVELS.index(level) > _LEVELS.index(worst):
            worst = level
    return worst, concerns


def _mb(n_bytes: int | float) -> float:
    return round(n_bytes / (1024 * 1024), 1)


def _gb(n_bytes: int | float) -> float:
    return round(n_bytes / (1024 * 1024 * 1024), 2)


def _net_rates(now: float, sent: int, recv: int) -> dict[str, float | None]:
    """KB/s since the previous sample; None until two samples exist."""
    global _last_net
    rates: dict[str, float | None] = {"sent_kbps": None, "recv_kbps": None}
    if _last_net is not None:
        prev_ts, prev_sent, prev_recv = _last_net
        elapsed = now - prev_ts
        # Counters reset on reboot/interface flap; skip nonsensical deltas.
        if elapsed > 0 and sent >= prev_sent and recv >= prev_recv:
            rates["sent_kbps"] = round((sent - prev_sent) / elapsed / 1024, 2)
            rates["recv_kbps"] = round((recv - prev_recv) / elapsed / 1024, 2)
    _last_net = (now, sent, recv)
    return rates


def sample() -> dict[str, Any]:
    """Take one telemetry sample, append it to history, and emit alerts on
    health-level transitions. Never raises past psutil failures per-section."""
    global _last_status
    now = time.time()
    snapshot: dict[str, Any] = {"ts": datetime.now(UTC).isoformat()}

    cpu_pct = psutil.cpu_percent(interval=None)
    snapshot["cpu"] = {
        "percent": cpu_pct,
        "cores_logical": psutil.cpu_count(logical=True),
        "cores_physical": psutil.cpu_count(logical=False),
    }
    try:
        load1, load5, load15 = psutil.getloadavg()
        snapshot["cpu"]["load_avg"] = [round(load1, 2), round(load5, 2), round(load15, 2)]
    except (AttributeError, OSError):
        snapshot["cpu"]["load_avg"] = None

    mem = psutil.virtual_memory()
    snapshot["memory"] = {
        "total_mb": _mb(mem.total),
        "available_mb": _mb(mem.available),
        "percent": mem.percent,
    }
    swap = psutil.swap_memory()
    snapshot["swap"] = {
        "total_mb": _mb(swap.total),
        "used_mb": _mb(swap.used),
        "percent": swap.percent,
    }

    disk = psutil.disk_usage(str(ROOT))
    snapshot["disk"] = {
        "path": str(ROOT.anchor or ROOT),
        "total_gb": _gb(disk.total),
        "free_gb": _gb(disk.free),
        "percent": disk.percent,
    }

    try:
        net = psutil.net_io_counters()
        snapshot["network"] = {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            **_net_rates(now, net.bytes_sent, net.bytes_recv),
        }
    except Exception:
        snapshot["network"] = None

    try:
        with _self_process.oneshot():
            snapshot["process"] = {
                "pid": _self_process.pid,
                "rss_mb": _mb(_self_process.memory_info().rss),
                "cpu_percent": _self_process.cpu_percent(interval=None),
                "threads": _self_process.num_threads(),
            }
    except psutil.Error:
        snapshot["process"] = None

    boot = psutil.boot_time()
    snapshot["system"] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "process_count": len(psutil.pids()),
        "uptime_seconds": int(now - boot),
    }

    status, concerns = _verdict(cpu_pct, mem.percent, disk.percent)
    snapshot["status"] = status
    snapshot["concerns"] = concerns

    _history.append(snapshot)
    if status != _last_status:
        emit_os_alert(status=status, previous=_last_status, concerns=concerns)
        _last_status = status
    return snapshot


def get_os_metrics(include_processes: bool = False, top_n: int = 5) -> dict[str, Any]:
    """Current snapshot, optionally with the top-N processes by memory."""
    snapshot = sample()
    if include_processes:
        snapshot["top_processes"] = _top_processes(top_n)
    return snapshot


def _top_processes(top_n: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            mem_info = proc.info["memory_info"]
            rows.append(
                {
                    "pid": proc.info["pid"],
                    "name": proc.info["name"],
                    "rss_mb": _mb(mem_info.rss) if mem_info else 0.0,
                }
            )
        except psutil.Error:
            continue
    rows.sort(key=lambda r: r["rss_mb"], reverse=True)
    return rows[: max(1, min(top_n, 20))]


def get_history(limit: int = 120) -> list[dict[str, Any]]:
    """Most recent samples, oldest first."""
    items = list(_history)
    return items[-limit:]


async def sampler_loop() -> None:
    """Background sampler for continuous history + alerting between requests."""
    while True:
        try:
            sample()
        except Exception:
            pass
        await asyncio.sleep(settings.os_monitor_interval_seconds)
