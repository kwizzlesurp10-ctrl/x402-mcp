"""Multiprocess coordination against a real loopback ``redis-server`` (not fakeredis).

Opt out: ``X402_REDIS_MP_TESTS=0``. Requires ``redis-server`` on PATH (e.g. apt install).

Two OS processes import the app with ``REDIS_URL`` pointed at an isolated instance
so ``redis_client.client`` and module singletons are fresh per interpreter.
"""

from __future__ import annotations

import json
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tests.redis_mp_helpers import (
    isolated_redis_server,
    requires_real_redis_mp,
    run_python_snippet,
)

_REPO_ROOT = str(Path(__file__).resolve().parents[1])


def _snippet_policy_delivery_concurrent(url: str, claim_key: str, input_digest: str) -> str:
    return textwrap.dedent(
        f"""
        import asyncio
        import json
        import os
        import sys
        from pathlib import Path

        ROOT = Path(r"{_REPO_ROOT}")
        sys.path.insert(0, str(ROOT))

        os.environ["REDIS_URL"] = {url!r}
        os.environ.pop("REDIS_TEST_URL", None)

        from app.config import settings
        from app import redis_client

        settings.redis_url = os.environ["REDIS_URL"]
        settings.policy_check_idempotency_redis_strict = True
        redis_client.fallback_reason = None
        redis_client.client = redis_client.build_client()
        assert redis_client.client is not None

        from app import policy_check

        _settle_calls = {{}}

        async def _fake_settle(_s, _h):
            _settle_calls["n"] = _settle_calls.get("n", 0) + 1
            return {{
                "is_valid": True,
                "payment_settled": True,
                "settlement": {{
                    "success": True,
                    "transaction": "0xmpcoord",
                    "payer": "0xPayerMp00000000000000000000000001",
                }},
            }}

        policy_check.settle_payment_only = _fake_settle

        async def main():
            st, rec = await policy_check.delivery_try_claim_or_hit_async(
                {claim_key!r}, {input_digest!r}
            )
            out = {{"claim_first": st, "settle_calls": 0}}
            if st == "claimed_new":
                await policy_check.settle_payment_only("sig", "hdr")
                out["settle_calls"] = _settle_calls.get("n", 0)
                body = {{"verdict": "pass", "probe": "mp-a"}}
                ok, prev = await policy_check.delivery_write_final_async(
                    {claim_key!r},
                    input_digest={input_digest!r},
                    body=body,
                    payment_proof_fp="pf",
                )
                out["write_ok"] = ok
            elif st == "claimed_busy":
                waited = await policy_check.delivery_wait_for_final_async(
                    {claim_key!r}, {input_digest!r}
                )
                out["waited_body"] = waited
                out["settle_calls"] = _settle_calls.get("n", 0)
            elif st == "final_hit" and isinstance(rec, dict):
                out["from_cache"] = True
                out["settle_calls"] = _settle_calls.get("n", 0)
            else:
                out["unexpected"] = st
            print(json.dumps(out))

        asyncio.run(main())
        """
    )


def _snippet_policy_delivery_conflict(url: str, claim_key: str, digest_a: str, digest_b: str) -> str:
    return textwrap.dedent(
        f"""
        import asyncio
        import json
        import os
        import sys
        from pathlib import Path

        ROOT = Path(r"{_REPO_ROOT}")
        sys.path.insert(0, str(ROOT))

        os.environ["REDIS_URL"] = {url!r}

        from app.config import settings
        from app import redis_client

        settings.redis_url = os.environ["REDIS_URL"]
        settings.policy_check_idempotency_redis_strict = True
        redis_client.fallback_reason = None
        redis_client.client = redis_client.build_client()

        from app import policy_check

        _settle_calls = {{}}

        async def _fake_settle(_s, _h):
            _settle_calls["n"] = _settle_calls.get("n", 0) + 1
            return {{
                "is_valid": True,
                "payment_settled": True,
                "settlement": {{"success": True, "transaction": "0xc"}},
            }}

        policy_check.settle_payment_only = _fake_settle

        role = os.environ["ROLE"]

        async def main():
            if role == "a":
                st, _ = await policy_check.delivery_try_claim_or_hit_async({claim_key!r}, {digest_a!r})
                assert st == "claimed_new", st
                await policy_check.settle_payment_only("s", "h")
                await policy_check.delivery_write_final_async(
                    {claim_key!r},
                    input_digest={digest_a!r},
                    body={{"ok": True}},
                    payment_proof_fp="p",
                )
                print(json.dumps({{"role": "a", "settle_calls": _settle_calls.get("n", 0)}}))
            else:
                st, _ = await policy_check.delivery_try_claim_or_hit_async({claim_key!r}, {digest_b!r})
                sc = _settle_calls.get("n", 0)
                print(json.dumps({{"role": "b", "claim": st, "settle_calls": sc}}))

        asyncio.run(main())
        """
    )


def _snippet_a2a_cas_contend(url: str, task_id: str) -> str:
    return textwrap.dedent(
        f"""
        import json
        import os
        import sys
        from pathlib import Path

        ROOT = Path(r"{_REPO_ROOT}")
        sys.path.insert(0, str(ROOT))

        os.environ["REDIS_URL"] = {url!r}

        from app.config import settings
        from app import redis_client, a2a_task_store

        settings.redis_url = os.environ["REDIS_URL"]
        settings.a2a_task_store_redis = True
        settings.a2a_task_store_redis_strict = True
        redis_client.fallback_reason = None
        redis_client.client = redis_client.build_client()

        marker = os.environ["MARKER"]
        base = json.loads(os.environ["TASK_BASE_JSON"])

        upd = dict(base)
        upd["mp_marker"] = marker
        ok = a2a_task_store.put_task({task_id!r}, upd)
        print(json.dumps({{"marker": marker, "ok": ok}}))
        """
    )


def _snippet_mcp_lock(url: str, composite: str) -> str:
    return textwrap.dedent(
        f"""
        import json
        import os
        import sys
        from pathlib import Path

        ROOT = Path(r"{_REPO_ROOT}")
        sys.path.insert(0, str(ROOT))

        os.environ["REDIS_URL"] = {url!r}
        os.environ["MCP_COMMERCE_REDIS_STRICT"] = "true"

        # Import order: refresh mcp_settlement_store client after settings
        from app.config import settings
        from app import redis_client

        settings.redis_url = os.environ["REDIS_URL"]
        settings.mcp_commerce_redis_strict = True
        redis_client.fallback_reason = None
        redis_client.client = redis_client.build_client()

        from app import mcp_settlement_store

        mcp_settlement_store.refresh_client()

        acq, token, err = mcp_settlement_store.acquire_settlement_lock({composite!r})
        print(json.dumps({{"acquired": acq, "token": token is not None, "redis_error": err}}))
        """
    )


def _snippet_strict_redis_down() -> str:
    return textwrap.dedent(
        f"""
        import os
        import sys
        from pathlib import Path

        ROOT = Path(r"{_REPO_ROOT}")
        sys.path.insert(0, str(ROOT))

        os.environ["REDIS_URL"] = "redis://127.0.0.1:1"
        from app.config import settings
        from app import redis_client

        settings.redis_url = os.environ["REDIS_URL"]
        settings.policy_check_idempotency_redis_strict = True
        redis_client.fallback_reason = None
        redis_client.client = None

        from app import policy_check

        ok = policy_check.idempotency_strict_redis_unavailable()
        print("strict_unavailable=%s" % ok)
        """
    )


@requires_real_redis_mp
def test_policy_delivery_two_processes_single_settle() -> None:
    claim_key = "a" * 64
    input_digest = "b" * 64
    with isolated_redis_server() as (_proc, url):
        code = _snippet_policy_delivery_concurrent(url, claim_key, input_digest)
        env_base = {"PYTHONUNBUFFERED": "1"}

        def _run() -> dict[str, object]:
            out = run_python_snippet(code, env=env_base)
            return json.loads(out)

        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = [ex.submit(_run), ex.submit(_run)]
            results = [f.result() for f in as_completed(futs)]

        primary = [r for r in results if r.get("claim_first") == "claimed_new"]
        follower = [
            r
            for r in results
            if r.get("claim_first") in ("claimed_busy", "final_hit")
            or r.get("from_cache")
        ]
        assert len(primary) == 1 and len(follower) == 1, results
        assert "unexpected" not in primary[0] and "unexpected" not in follower[0]
        settle_total = sum(int(r.get("settle_calls", 0)) for r in results)
        assert settle_total == 1
        assert int(follower[0].get("settle_calls", -1)) == 0


@requires_real_redis_mp
def test_policy_delivery_digest_conflict_no_second_settle() -> None:
    claim_key = "c" * 64
    digest_a = "d" * 64
    digest_b = "e" * 64
    with isolated_redis_server() as (_proc, url):
        code = _snippet_policy_delivery_conflict(url, claim_key, digest_a, digest_b)

        def run_a() -> dict[str, object]:
            return json.loads(run_python_snippet(code, env={"ROLE": "a", "PYTHONUNBUFFERED": "1"}))

        def run_b() -> dict[str, object]:
            return json.loads(run_python_snippet(code, env={"ROLE": "b", "PYTHONUNBUFFERED": "1"}))

        ra = run_a()
        rb = run_b()

        assert ra["role"] == "a"
        assert ra["settle_calls"] == 1
        assert rb["claim"] == "conflict"
        assert rb["settle_calls"] == 0


@requires_real_redis_mp
def test_a2a_task_cas_two_writers_one_strict_failure() -> None:
    task_id = "mp-coord-task-1"
    with isolated_redis_server() as (_proc, url):
        from app import a2a_task_store, redis_client
        from app.config import settings

        settings.redis_url = url
        settings.a2a_task_store_redis = True
        settings.a2a_task_store_redis_strict = True
        redis_client.fallback_reason = None
        redis_client.client = redis_client.build_client()
        assert redis_client.client is not None

        seed = {
            "id": task_id,
            "status": {"state": "submitted"},
            "metadata": {"skillId": "us-cities-catalog", "input": {}},
        }
        assert a2a_task_store.put_task(task_id, seed) is True
        loaded = a2a_task_store.get_task(task_id)
        assert loaded is not None and loaded.get("_a2a_rev") == 1
        base_json = json.dumps(loaded, sort_keys=True)

        code = _snippet_a2a_cas_contend(url, task_id)
        env_common = {
            "TASK_BASE_JSON": base_json,
            "PYTHONUNBUFFERED": "1",
        }
        with ThreadPoolExecutor(max_workers=2) as ex:
            fa = ex.submit(
                run_python_snippet,
                code,
                env={**env_common, "MARKER": "worker-a"},
            )
            fb = ex.submit(
                run_python_snippet,
                code,
                env={**env_common, "MARKER": "worker-b"},
            )
            ja = json.loads(fa.result())
            jb = json.loads(fb.result())

        assert ja["ok"] is True or jb["ok"] is True
        assert ja["ok"] is False or jb["ok"] is False


@requires_real_redis_mp
def test_mcp_settlement_lock_excludes_second_process() -> None:
    composite = "mp-lock-test-composite"
    with isolated_redis_server() as (_proc, url):
        code = _snippet_mcp_lock(url, composite)
        env = {"PYTHONUNBUFFERED": "1"}
        r1 = json.loads(run_python_snippet(code, env=env))
        r2 = json.loads(run_python_snippet(code, env=env))
        assert r1["acquired"] is True
        assert r1["redis_error"] is False
        assert r2["acquired"] is False
        assert r2["redis_error"] is False


def test_subprocess_strict_idempotency_flags_redis_unreachable_without_live_redis() -> None:
    out = run_python_snippet(_snippet_strict_redis_down(), env={"PYTHONUNBUFFERED": "1"})
    assert "strict_unavailable=True" in out
