"""Low-cardinality latency samples for server-observable x402/A2A stages.

Cardinality policy:
- ``bucket``: coarse surface only (e.g. ``a2a``, ``mcp_commerce``, ``verify_settle_http``).
- ``stage``: fixed enum-like string per bucket (challenge_build, redis_read, …).

Client-side signing and chain finality are **not** observable here unless you
correlate with client-provided spans — do not label loop timings as "signing".

Percentiles are computed from in-process ring buffers (default 8000 samples per
pair). For production dashboards, scrape ``GET /stats`` (operator) or export
OpenTelemetry later; this module is the minimal single-host view.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from typing import Any

_MAX_SAMPLES = 8000

_lock = threading.Lock()
_buffers: dict[tuple[str, str], deque[float]] = defaultdict(
    lambda: deque(maxlen=_MAX_SAMPLES)
)


def record_seconds(bucket: str, stage: str, seconds: float) -> None:
    if seconds < 0 or math.isnan(seconds):
        return
    key = (bucket, stage)
    with _lock:
        _buffers[key].append(seconds)


def record_span(bucket: str, stage: str, start_perf: float) -> None:
    record_seconds(bucket, stage, time.perf_counter() - start_perf)


def snapshot() -> dict[str, Any]:
    """Return p50/p95/p99 and n per (bucket, stage); omits empty buffers."""
    with _lock:
        keys = list(_buffers.keys())
    out: dict[str, Any] = {}
    for key in keys:
        with _lock:
            samples = list(_buffers.get(key) or ())
        if not samples:
            continue
        bucket, stage = key
        samples.sort()
        n = len(samples)

        def _pct(p: float) -> float:
            if n == 1:
                return samples[0]
            idx = min(n - 1, max(0, int(math.ceil(p * n) - 1)))
            return samples[idx]

        name = f"{bucket}/{stage}"
        out[name] = {
            "n": n,
            "p50": round(_pct(0.50), 6),
            "p95": round(_pct(0.95), 6),
            "p99": round(_pct(0.99), 6),
        }
    return {"x402_latency_seconds": out, "note": "server_observable_only"}


def clear_for_test() -> None:
    with _lock:
        _buffers.clear()
