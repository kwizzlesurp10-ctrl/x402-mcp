#!/usr/bin/env python3
"""Reproducible A2A + MCP latency harness (mock facilitator, no mainnet spend).

Covers: paid challenge build (sequential + concurrent), full verify/settle/fulfill
with configurable mock delays, duplicate payment retry, Redis strict write
injection, and event-loop lag under concurrent async load.

When ``REDIS_URL`` is set, ``_install_fakeredis_if_configured`` binds the shared
Redis client to ``fakeredis`` (same pattern as tests). Fakeredis is single-
process and not a stand-in for Redis Cluster or real network behavior; call
that out in benchmark reports.

Usage (from repo root)::

  export X402_PAY_TO_ADDRESS=0x0d25A44f74868eCE53B305C97139CF4B62963410
  export REDIS_URL=redis://fake
  python scripts/benchmark_x402_latency.py --json-out /opt/cursor/artifacts/a2a_bench.json

Environment:
  BENCH_WARMUP (default 15), BENCH_SAMPLES (default 120), BENCH_CONCURRENCY (8),
  BENCH_MOCK_VERIFY_MS (12), BENCH_MOCK_SETTLE_MS (8), BENCH_MOCK_EXECUTE_MS (3),
  BENCH_PAID_SAMPLES (40) — capped paid-path iterations (each includes settle).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


WARMUP = _env_int("BENCH_WARMUP", 15)
SAMPLES = _env_int("BENCH_SAMPLES", 120)
CONCURRENCY = _env_int("BENCH_CONCURRENCY", 8)
PAID_SAMPLES = _env_int("BENCH_PAID_SAMPLES", 40)
MOCK_VERIFY_MS = _env_float("BENCH_MOCK_VERIFY_MS", 12.0)
MOCK_SETTLE_MS = _env_float("BENCH_MOCK_SETTLE_MS", 8.0)
MOCK_EXECUTE_MS = _env_float("BENCH_MOCK_EXECUTE_MS", 3.0)


def _pct(sorted_samples: list[float], p: float) -> float:
    n = len(sorted_samples)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_samples[0]
    idx = min(n - 1, max(0, int(math.ceil(p * n) - 1)))
    return sorted_samples[idx]


def _summarize(
    name: str,
    times: list[float],
    *,
    errors: int = 0,
    wall_seconds: float | None = None,
) -> dict[str, Any]:
    s = sorted(times)
    elapsed_wall = float(wall_seconds or 0)
    tput = (len(s) / elapsed_wall) if elapsed_wall > 0 else None
    return {
        "name": name,
        "n": len(s),
        "errors": errors,
        "p50_ms": round(_pct(s, 0.50) * 1000, 3),
        "p95_ms": round(_pct(s, 0.95) * 1000, 3),
        "p99_ms": round(_pct(s, 0.99) * 1000, 3),
        "mean_ms": round(statistics.mean(s) * 1000, 3) if s else 0,
        "throughput_per_s": round(tput, 3) if tput is not None else None,
    }


def _install_fakeredis_if_configured() -> None:
    if not os.environ.get("REDIS_URL"):
        return
    import fakeredis

    from app import commerce, mcp_settlement_store, redis_client
    from app.config import settings

    r = fakeredis.FakeRedis(decode_responses=True)
    redis_client.client = r
    redis_client.fallback_reason = None
    commerce.quota_store = commerce.build_quota_store()
    mcp_settlement_store._CLIENT = r
    settings.redis_url = os.environ.get("REDIS_URL", "redis://fake")
    # Baseline commits may lack newer Settings fields — skip when absent.
    fields = getattr(settings.__class__, "model_fields", None)
    if isinstance(fields, dict) and "a2a_task_store_redis" in fields:
        settings.a2a_task_store_redis = True  # type: ignore[misc]


def run_challenge_build_sequential() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app.agent_surface import A2A_X402_EXTENSION_URI
    from app.a2a_rpc import clear_task_store
    from app.main import app

    clear_task_store()
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
        assert resp.status_code == 200, resp.text
        times.append(time.perf_counter() - t0)

    for _ in range(WARMUP):
        one()
    times.clear()
    wall0 = time.perf_counter()
    for _ in range(SAMPLES):
        one()
    wall_s = time.perf_counter() - wall0
    return _summarize("a2a_challenge_build_sequential", times, wall_seconds=wall_s)


def run_challenge_build_concurrent() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app.agent_surface import A2A_X402_EXTENSION_URI
    from app.a2a_rpc import clear_task_store
    from app.main import app

    clear_task_store()
    client = TestClient(app)
    times: list[float] = []
    err_count = [0]

    def one() -> None:
        clear_task_store()
        t0 = time.perf_counter()
        try:
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
            if resp.status_code != 200:
                err_count[0] += 1
        except Exception:  # noqa: BLE001
            err_count[0] += 1
        times.append(time.perf_counter() - t0)

    wall0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = [ex.submit(one) for _ in range(SAMPLES)]
        for f in as_completed(futs):
            f.result()
    wall_s = time.perf_counter() - wall0
    return _summarize(
        f"a2a_challenge_build_concurrent_workers_{CONCURRENCY}",
        times,
        errors=err_count[0],
        wall_seconds=wall_s,
    )


def _patch_base_tx_binding(
    verify_settle: Any,
    execute: Any,
    *,
    record_revenue: Any = None,
):
    from app import a2a_rpc as M

    orig = M._skill_bindings

    def _over() -> dict:
        out = dict(orig())
        b0 = out["base-tx-decision"]
        # Must stay a real SkillBinding so paid continuations pass isinstance() in a2a_rpc.
        out["base-tx-decision"] = replace(
            b0,
            record_revenue=record_revenue,
            verify_and_settle=verify_settle,
            execute=execute,
        )
        return out

    M._skill_bindings = _over  # type: ignore[method-assign]

    def restore() -> None:
        M._skill_bindings = orig  # type: ignore[method-assign]

    return restore


def _minimal_payload_from_payment_required_header(header: str) -> dict[str, Any]:
    from x402.http import decode_payment_required_header

    pr = decode_payment_required_header(header)
    accept = pr.accepts[0]
    return {
        "x402Version": 2,
        "payload": {"signature": "0x", "authorization": {}},
        "accepted": accept.model_dump(by_alias=True, exclude_none=True),
    }


def run_paid_path_with_mock_delays() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app import a2a_task_store
    from app.agent_surface import A2A_X402_EXTENSION_URI
    from app.a2a_rpc import META_STATUS, clear_task_store
    from app.config import settings
    from app.main import app

    settle_calls = {"n": 0}

    async def _verify_settle(_sig: str, _header: str) -> dict[str, Any]:
        settle_calls["n"] += 1
        await asyncio.sleep(MOCK_VERIFY_MS / 1000.0)
        await asyncio.sleep(MOCK_SETTLE_MS / 1000.0)
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {
                "success": True,
                "transaction": "0xabc001",
                "network": settings.x402_default_network,
            },
        }

    async def _execute(_inp: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(MOCK_EXECUTE_MS / 1000.0)
        return {"paid_bench": True}

    restore = _patch_base_tx_binding(_verify_settle, _execute, record_revenue=None)
    clear_task_store()
    client = TestClient(app)
    times: list[float] = []
    wall_s = 0.0
    try:
        for _ in range(max(3, WARMUP // 5)):
            clear_task_store()
            client.post(
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
        settle_calls["n"] = 0
        n_run = max(1, min(PAID_SAMPLES, SAMPLES))
        wall0 = time.perf_counter()
        for _ in range(n_run):
            clear_task_store()
            t0 = time.perf_counter()
            start = client.post(
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
            assert start.status_code == 200
            tid = start.json()["result"]["id"]
            cap = start.json()["result"].get("capabilityToken")
            stored_hdr = a2a_task_store.get_task(tid) or {}
            pay_header = stored_hdr.get("payment_required_header")
            assert isinstance(pay_header, str)
            body = _minimal_payload_from_payment_required_header(pay_header)
            pay = client.post(
                "/a2a",
                json={
                    "jsonrpc": "2.0",
                    "id": "2",
                    "method": "message/send",
                    "params": {
                        "message": {
                            "role": "user",
                            "parts": [],
                            "taskId": tid,
                            "metadata": {
                                META_STATUS: "payment-submitted",
                                **({"x402.task.capability": cap} if cap else {}),
                                "x402.payment.payload": body,
                            },
                        }
                    },
                },
            )
            assert pay.status_code == 200
            assert pay.json()["result"]["status"]["state"] == "completed"
            times.append(time.perf_counter() - t0)
        wall_s = time.perf_counter() - wall0
    finally:
        restore()

    summ = _summarize("a2a_paid_verify_settle_execute_mock_delays", times, wall_seconds=wall_s)
    summ["mock_delays_ms"] = {
        "verify": MOCK_VERIFY_MS,
        "settle": MOCK_SETTLE_MS,
        "execute": MOCK_EXECUTE_MS,
    }
    summ["verify_settle_calls"] = settle_calls["n"]
    summ["paid_iterations"] = len(times)
    return summ


def run_duplicate_payment_retry() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from app import a2a_task_store
    from app.agent_surface import A2A_X402_EXTENSION_URI
    from app.a2a_rpc import META_STATUS, clear_task_store
    from app.config import settings
    from app.main import app

    settle_calls = {"n": 0}

    async def _verify_settle(_sig: str, _header: str) -> dict[str, Any]:
        settle_calls["n"] += 1
        await asyncio.sleep(MOCK_VERIFY_MS / 1000.0)
        await asyncio.sleep(MOCK_SETTLE_MS / 1000.0)
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {
                "success": True,
                "transaction": "0xdupretry",
                "network": settings.x402_default_network,
            },
        }

    async def _execute(_inp: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(MOCK_EXECUTE_MS / 1000.0)
        return {"dup": True}

    restore = _patch_base_tx_binding(_verify_settle, _execute)
    clear_task_store()
    client = TestClient(app)
    try:
        start = client.post(
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
        tid = start.json()["result"]["id"]
        cap = start.json()["result"].get("capabilityToken")
        hdr = (a2a_task_store.get_task(tid) or {}).get("payment_required_header")
        assert isinstance(hdr, str)
        body = _minimal_payload_from_payment_required_header(hdr)
        pay = {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [],
                    "taskId": tid,
                    "metadata": {
                        META_STATUS: "payment-submitted",
                        **({"x402.task.capability": cap} if cap else {}),
                        "x402.payment.payload": body,
                    },
                }
            },
        }
        settle_calls["n"] = 0
        r1 = client.post("/a2a", json=pay)
        r2 = client.post("/a2a", json=pay)
        assert r1.json()["result"]["status"]["state"] == "completed"
        assert r2.json()["result"]["status"]["state"] == "completed"
    finally:
        restore()
    return {
        "name": "duplicate_payment_submit_retry_semantics",
        "verify_settle_call_count": settle_calls["n"],
        "note": "Second identical payment-submitted should skip verify+settle when receipt has tx",
    }


def run_redis_write_failure_flag() -> dict[str, Any]:
    from app import a2a_task_store
    from app.config import settings

    if not a2a_task_store.durable_enabled():
        return {"name": "redis_injection", "skipped": True, "reason": "durable store not active"}

    r = a2a_task_store._redis()
    if r is None:
        return {"name": "redis_injection", "skipped": True, "reason": "no redis client"}

    strict_field = getattr(settings.__class__, "model_fields", None)
    has_strict = isinstance(strict_field, dict) and "a2a_task_store_redis_strict" in strict_field
    if not has_strict:
        return {
            "name": "redis_strict_write_injection",
            "skipped": True,
            "reason": "A2A_TASK_STORE_REDIS_STRICT not in Settings on this checkout",
        }

    orig_set = r.set
    failures = {"n": 0}
    strict_before = settings.a2a_task_store_redis_strict

    def boom_set(*a: Any, **kw: Any) -> Any:
        failures["n"] += 1
        raise ConnectionError("injected")

    try:
        r.set = boom_set  # type: ignore[method-assign]
        settings.a2a_task_store_redis_strict = True
        ok = a2a_task_store.put_task("inj", {"id": "inj", "status": {"state": "failed"}})
    finally:
        r.set = orig_set  # type: ignore[method-assign]
        settings.a2a_task_store_redis_strict = strict_before
        a2a_task_store.delete_task("inj")

    return {
        "name": "redis_strict_write_injection",
        "put_returned_false": ok is False,
        "injected_errors": failures["n"],
    }


async def _event_loop_lag_under_concurrent_posts() -> dict[str, Any]:
    import httpx
    from httpx import ASGITransport

    from app.agent_surface import A2A_X402_EXTENSION_URI
    from app.a2a_rpc import clear_task_store
    from app.main import app

    clear_task_store()
    transport = ASGITransport(app=app)
    payload = {
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
    }
    n_load = min(SAMPLES, 80)
    interval = 0.02
    drifts: list[float] = []

    async def sleeper() -> None:
        expected = time.perf_counter()
        for _ in range(60):
            await asyncio.sleep(interval)
            now = time.perf_counter()
            drifts.append(max(0.0, now - expected - interval))
            expected = now

    async def load_client(c: httpx.AsyncClient) -> None:
        for _ in range(n_load):
            await c.post(
                "/a2a",
                headers={"X-A2A-Extensions": A2A_X402_EXTENSION_URI},
                json=payload,
            )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        t_load = asyncio.create_task(load_client(client))
        t_sleep = asyncio.create_task(sleeper())
        await t_load
        t_sleep.cancel()
        try:
            await t_sleep
        except asyncio.CancelledError:
            pass

    s = sorted(drifts)
    return {
        "name": "event_loop_lag_ms_under_async_load",
        "load_concurrent_posts": n_load,
        "probe_interval_s": interval,
        "n_drift_samples": len(s),
        "drift_p95_ms": round(_pct(s, 0.95) * 1000, 3) if s else 0,
        "drift_p99_ms": round(_pct(s, 0.99) * 1000, 3) if s else 0,
    }


def run_event_loop_probe() -> dict[str, Any]:
    return asyncio.run(_event_loop_lag_under_concurrent_posts())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Write full report JSON to this path",
    )
    args = parser.parse_args()

    if not os.environ.get("X402_PAY_TO_ADDRESS"):
        os.environ["X402_PAY_TO_ADDRESS"] = "0x0d25A44f74868eCE53B305C97139CF4B62963410"

    _install_fakeredis_if_configured()

    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        commit = os.environ.get("GIT_COMMIT", "")

    report: dict[str, Any] = {
        "warmup_iterations": WARMUP,
        "samples": SAMPLES,
        "paid_samples": PAID_SAMPLES,
        "concurrency": CONCURRENCY,
        "mock_delays_ms": {
            "verify": MOCK_VERIFY_MS,
            "settle": MOCK_SETTLE_MS,
            "execute": MOCK_EXECUTE_MS,
        },
        "git_commit": commit,
        "environment": "mock_facilitator_no_mainnet",
        "fakeredis_note": (
            "fakeredis is in-process and single-threaded; concurrency results "
            "do not model Redis Cluster or real network latency."
        ),
        "results": [
            run_challenge_build_sequential(),
            run_challenge_build_concurrent(),
            run_paid_path_with_mock_delays(),
            run_duplicate_payment_retry(),
            run_redis_write_failure_flag(),
            run_event_loop_probe(),
        ],
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
