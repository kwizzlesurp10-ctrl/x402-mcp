"""Concurrent A2A task writes against real local Redis (opt-in).

Set REDIS_URL to a disposable local instance (e.g. redis://127.0.0.1:6379/15)
and run:

  REDIS_URL=redis://127.0.0.1:6379/15 pytest tests/test_a2a_redis_cas_concurrent.py -q

Without REDIS_URL the module is skipped (CI / default agent env).
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _worker_cancel(task_id: str, url: str) -> str:
    os.environ["REDIS_URL"] = url
    # Import after env so settings pick up URL
    from app import a2a_task_store, redis_client
    from app.a2a_rpc import _agent_message, _task_dict
    from app.config import settings

    settings.redis_url = url
    settings.a2a_task_store_redis = True
    settings.a2a_task_store_redis_strict = True
    if redis_client.client is None:
        redis_client.client = redis_client.build_client()
    assert redis_client.client is not None

    raw = a2a_task_store.get_task(task_id)
    assert raw is not None
    msg = _agent_message("Task canceled by client.", {})
    raw.update(_task_dict(task_id=task_id, state="canceled", message=msg))
    ok = a2a_task_store.put_task(task_id, raw)
    return "ok" if ok else "fail"


@pytest.mark.skipif(
    not os.environ.get("REDIS_URL"),
    reason="REDIS_URL not set — use local redis for multiprocess CAS test",
)
def test_concurrent_cancel_wins_one_writer_real_redis() -> None:
    from app import a2a_task_store, redis_client
    from app.config import settings

    url = os.environ["REDIS_URL"]
    settings.redis_url = url
    settings.a2a_task_store_redis = True
    settings.a2a_task_store_redis_strict = True
    if redis_client.client is None:
        redis_client.client = redis_client.build_client()
    if redis_client.client is None:
        pytest.skip("REDIS_URL set but Redis unreachable — need a live redis for this test")

    a2a_task_store.clear_for_test()
    task_id = "mpcas1"
    base = {
        "kind": "task",
        "id": task_id,
        "status": {"state": "input-required"},
        "skillId": "us-cities-catalog",
    }
    assert a2a_task_store.put_task(task_id, dict(base))

    ctx = mp.get_context("spawn")
    p1 = ctx.Process(target=_worker_cancel, args=(task_id, url))
    p2 = ctx.Process(target=_worker_cancel, args=(task_id, url))
    p1.start()
    p2.start()
    p1.join(timeout=30)
    p2.join(timeout=30)
    assert p1.exitcode == 0 and p2.exitcode == 0

    time.sleep(0.05)
    final = a2a_task_store.get_task(task_id)
    assert final is not None
    assert (final.get("status") or {}).get("state") == "canceled"
