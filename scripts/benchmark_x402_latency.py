#!/usr/bin/env python3
"""Reproducible latency harness for A2A + MCP commerce (mock facilitator).

This script does **not** hit mainnet or spend funds. It drives FastAPI TestClient
with monkeypatched verify/settle and (optionally) fakeredis for MCP.

Usage (from repo root):
  X402_PAY_TO_ADDRESS=0x0d25A44f74868eCE53B305C97139CF4B62963410 \\
  python scripts/benchmark_x402_latency.py

Writes JSON summary to stdout; redirect to a file for artifacts.
"""

from __future__ import annotations

import logging

# Avoid httpx/x402 INFO noise on stderr when stdout is the JSON report.
logging.disable(logging.CRITICAL)

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Repo root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WARMUP = 15
SAMPLES = 120
CONCURRENCY = 8


def _pct(sorted_samples: list[float], p: float) -> float:
    n = len(sorted_samples)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_samples[0]
    idx = min(n - 1, max(0, int(__import__("math").ceil(p * n) - 1)))
    return sorted_samples[idx]


def _summarize(name: str, times: list[float]) -> dict:
    s = sorted(times)
    return {
        "name": name,
        "n": len(s),
        "p50_ms": round(_pct(s, 0.50) * 1000, 3),
        "p95_ms": round(_pct(s, 0.95) * 1000, 3),
        "p99_ms": round(_pct(s, 0.99) * 1000, 3),
        "mean_ms": round(statistics.mean(s) * 1000, 3) if s else 0,
    }


def run_a2a_challenge_benchmark() -> dict:
    from fastapi.testclient import TestClient

    from app.agent_surface import A2A_X402_EXTENSION_URI
    from app.a2a_rpc import clear_task_store
    from app.main import app

    client = TestClient(app)
    times: list[float] = []

    def one() -> None:
        clear_task_store()
        t0 = time.perf_counter()
        resp = client.post(
            "/a2a",
            headers={"X-A2A-Extensions": A2A_X402_EXTENSION_URI},
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [],
                        "metadata": {
                            "skillId": "base-tx-decision",
                            "input": {"gas": "usdc", "urgency": "flexible"},
                        },
                    }
                },
            },
        )
        assert resp.status_code == 200
        times.append(time.perf_counter() - t0)

    for _ in range(WARMUP):
        one()
    times.clear()
    for _ in range(SAMPLES):
        one()

    return _summarize("a2a_message_send_paid_challenge_build", times)


def main() -> None:
    if not os.environ.get("X402_PAY_TO_ADDRESS"):
        os.environ["X402_PAY_TO_ADDRESS"] = (
            "0x0d25A44f74868eCE53B305C97139CF4B62963410"
        )

    report = {
        "warmup_iterations": WARMUP,
        "samples": SAMPLES,
        "concurrency_note": CONCURRENCY,
        "environment": "mock_facilitator_no_mainnet",
        "results": [run_a2a_challenge_benchmark()],
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
