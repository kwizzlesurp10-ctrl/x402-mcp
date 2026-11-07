# PR #793 — real Redis, multiprocess coordination (local `redis-server`)

**Immutable HEAD (tests below):** `cb4e097`

Isolated loopback instance per test class/fixture: temp data dir, explicit key-prefix cleanup (no `FLUSHALL`), subprocesses do not inherit session `REDIS_URL` (`run_python_snippet` strips it).

## Environment

- **redis-server:** `Redis server v=7.0.15` (Ubuntu package `5:7.0.15-1ubuntu0.24.04.5` toolchain).
- **Evidence:** two (or more) independent OS processes (`python3 -c …`) share one `REDIS_URL` pointed at the spawned instance; coordination exercised for policy delivery, A2A task CAS, MCP settlement lock.

## Commands (repo root)

Default suite (`X402_REDIS_MP_TESTS` unset): multiprocess Redis tests are **skipped** (4); one subprocess always-on test runs (`strict_unavailable`).

```bash
python3 -m pytest -q --tb=line
# exit 0 — 1069 passed, 27 skipped (2026-11-06 agent run)
```

Multiprocess coordination module (requires `redis-server` on PATH):

```bash
X402_REDIS_MP_TESTS=1 python3 -m pytest tests/test_redis_multiprocess_coordination.py -v
# exit 0 — 5 passed
```

Full Python suite with multiprocess Redis tests enabled:

```bash
X402_REDIS_MP_TESTS=1 python3 -m pytest -q --tb=line
# exit 0 — 1073 passed, 23 skipped (2026-11-06 agent run)
```

Ruff (new files only):

```bash
ruff check tests/redis_mp_helpers.py tests/test_redis_multiprocess_coordination.py
# exit 0 — All checks passed!
```

## Not validated here

- **Upstash / TLS REST:** paths differ from local Valkey-compatible `redis-server` TCP.
- **Production readiness:** loopback-only; no claim this matches multi-region or provider limits.

## Residual gaps

- Policy delivery `SET NX` + finalize remains **non-transactional**; crash between settle and final write can leave ambiguous state (documented elsewhere; local Redis does not prove recovery semantics).
