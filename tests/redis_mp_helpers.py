"""Isolated loopback ``redis-server`` for multiprocess coordination tests.

Uses a dedicated data directory and key prefixes under test — never FLUSHALL/FLUSHDB.
Opt-in via ``X402_REDIS_MP_TESTS=1`` (or auto-enable when ``redis-server`` is found).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

_MP_TEST_ENV = "X402_REDIS_MP_TESTS"
_FIND_BIN = shutil.which("redis-server")


def real_redis_mp_enabled() -> bool:
    if os.environ.get(_MP_TEST_ENV, "").lower() in ("0", "false", "no"):
        return False
    # Opt-in only: avoids CI/envs without `redis-server` and keeps the default suite hermetic.
    if os.environ.get(_MP_TEST_ENV, "").lower() in ("1", "true", "yes"):
        return _FIND_BIN is not None
    return False


requires_real_redis_mp = pytest.mark.skipif(
    not real_redis_mp_enabled(),
    reason="Set X402_REDIS_MP_TESTS=1 and install redis-server (opt-in multiprocess suite)",
)


def _free_loopback_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    _host, port = s.getsockname()
    s.close()
    return int(port)


def _clear_prefixed_keys(client: Any, prefixes: tuple[str, ...]) -> None:
    if client is None:
        return
    try:
        for prefix in prefixes:
            for key in client.scan_iter(match=prefix + "*", count=64):
                client.delete(key)
    except Exception:  # noqa: BLE001, S110 — test cleanup; server may be torn down
        pass


@contextmanager
def isolated_redis_server(
    *,
    extra_clear_prefixes: tuple[str, ...] = (),
) -> Iterator[tuple[subprocess.Popen[str], str]]:
    """Spawn ``redis-server`` on 127.0.0.1 with a fresh RDB directory.

    Yields ``(process, redis_url)``. Terminates the server and removes the dir on exit.
    """
    if not _FIND_BIN:
        raise RuntimeError("redis-server binary not found")

    port = _free_loopback_port()
    data_dir = tempfile.mkdtemp(prefix="x402-redis-mp-")
    conf = Path(data_dir) / "redis.conf"
    conf.write_text(
        "\n".join(
            [
                "bind 127.0.0.1",
                f"port {port}",
                "daemonize no",
                "protected-mode yes",
                f"dir {data_dir}",
                "dbfilename mp-coord.rdb",
                "appendonly no",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        [_FIND_BIN, str(conf)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    url = f"redis://127.0.0.1:{port}/0"
    try:
        import redis as redis_mod

        deadline = time.monotonic() + 8.0
        client: Any = None
        while time.monotonic() < deadline:
            try:
                client = redis_mod.Redis.from_url(
                    url,
                    decode_responses=True,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                )
                client.ping()
                break
            except Exception:  # noqa: BLE001
                if proc.poll() is not None:
                    err = proc.stderr.read().decode() if proc.stderr else ""
                    raise RuntimeError(f"redis-server exited early: {err}") from None
                time.sleep(0.05)
        else:
            proc.terminate()
            raise RuntimeError("redis-server did not accept connections")

        assert client is not None
        prefixes = (
            "policy_check:delivery:",
            "a2a:task:",
            "mcp_settle:",
        ) + extra_clear_prefixes
        _clear_prefixed_keys(client, prefixes)
        try:
            client.close()
        except Exception:  # noqa: BLE001, S110
            pass
        yield proc, url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(data_dir, ignore_errors=True)


def run_python_snippet(code: str, *, env: dict[str, str], timeout: float = 30.0) -> str:
    """Run ``code`` in a fresh interpreter with ``env`` merged into environ."""
    import sys

    merged = {**os.environ, **env}
    merged.pop("REDIS_URL", None)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=merged,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"subprocess failed rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return proc.stdout.strip()
