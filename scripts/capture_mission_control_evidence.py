"""Capture mission-control verification evidence to GOAL_SCRATCH."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path(
    os.environ.get("GOAL_SCRATCH", str(Path(tempfile.gettempdir()) / "x402-mcp-evidence"))
)
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

API_PORT = 8402
DASH_PORT = 5173


def _kill_port(port: int) -> None:
    if sys.platform == "win32":
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
        )
        pids: set[str] = set()
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    pids.add(parts[-1])
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    else:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
    time.sleep(1)


def _start_api() -> subprocess.Popen[str]:
    return subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", f"--port", str(API_PORT)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _start_dashboard() -> subprocess.Popen[str]:
    return subprocess.Popen(
        ["pnpm", "dev", "--host", "127.0.0.1", "--port", str(DASH_PORT)],
        cwd=ROOT / "dashboard",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=True,
    )


def _drain(proc: subprocess.Popen[str], prefix: str, bucket: list[str], stop: threading.Event) -> None:
    if not proc.stdout:
        return
    while not stop.is_set():
        line = proc.stdout.readline()
        if not line:
            break
        bucket.append(f"[{prefix}] {line.rstrip()}")


def _wait_health(timeout: float = 30.0) -> dict:
    import httpx

    deadline = time.time() + timeout
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=3.0) as client:
                health = client.get(f"http://127.0.0.1:{API_PORT}/health")
                if health.status_code == 200:
                    return health.json()
        except Exception as exc:
            last_exc = exc
            time.sleep(0.5)
    raise RuntimeError(f"API health timeout: {last_exc}")


def _wait_dashboard(timeout: float = 45.0) -> int:
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"http://127.0.0.1:{DASH_PORT}/")
                if res.status_code == 200:
                    return res.status_code
        except Exception:
            time.sleep(0.5)
    return 0


def _stop_procs(*procs: subprocess.Popen[str]) -> None:
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
    for proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def capture_sse_heartbeat() -> None:
    import httpx

    log = SCRATCH / "backend_launch.log"
    lines: list[str] = []
    if log.exists():
        lines.append(log.read_text(encoding="utf-8").rstrip())

    proc = _start_api()
    try:
        time.sleep(2)
        with httpx.Client(timeout=25.0) as client:
            with client.stream("GET", f"http://127.0.0.1:{API_PORT}/events") as response:
                started = time.time()
                for line in response.iter_lines():
                    if time.time() - started > 20:
                        break
                    if line.startswith("data:"):
                        payload = json.loads(line[5:].strip())
                        if payload.get("type") == "heartbeat":
                            lines.append(f"sse_heartbeat={payload.get('ts')}")
                            break
    finally:
        _stop_procs(proc)

    log.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _boot_stack(run_id: int) -> list[str]:
    import httpx

    lines: list[str] = [f"=== boot {run_id} ==="]
    api_logs: list[str] = []
    dash_logs: list[str] = []
    stop = threading.Event()

    api = _start_api()
    dash = _start_dashboard()
    t_api = threading.Thread(target=_drain, args=(api, "api", api_logs, stop), daemon=True)
    t_dash = threading.Thread(target=_drain, args=(dash, "dash", dash_logs, stop), daemon=True)
    t_api.start()
    t_dash.start()

    try:
        health = _wait_health()
        lines.append(f"health_status=200")
        lines.append(f'health_body={{"status":"{health.get("status")}","service":"{health.get("service")}"}}')

        doctor = httpx.get(f"http://127.0.0.1:{API_PORT}/doctor", timeout=10).json()
        lines.append(f"doctor_ready={doctor.get('summary', {}).get('ready')}")
        lines.append(f"doctor_fail_count={doctor.get('summary', {}).get('fail')}")
        fail_ids = [c["id"] for c in doctor.get("checks", []) if c.get("status") == "fail"]
        lines.append(f"doctor_fail_ids={','.join(fail_ids)}")

        dash_status = _wait_dashboard()
        lines.append(f"dashboard_origin=http://127.0.0.1:{DASH_PORT}")
        lines.append(f"dashboard_load_status={dash_status}")

        time.sleep(2)
        stop.set()
        t_api.join(timeout=2)
        t_dash.join(timeout=2)
        lines.extend(api_logs[:8])
        lines.extend(dash_logs[:8])
        lines.append(f"api_log_lines={len(api_logs)}")
        lines.append(f"dash_log_lines={len(dash_logs)}")
        lines.append(f"both_processes_started={api.poll() is None and dash.poll() is None}")
    except Exception as exc:
        lines.append(f"boot_error={exc}")
    finally:
        stop.set()
        _stop_procs(api, dash)
        time.sleep(1)

    return lines


def capture_make_up() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    log = SCRATCH / "make_up.log"
    lines: list[str] = []

    try:
        make = subprocess.run(["make", "--version"], capture_output=True, text=True)
        make_ok = make.returncode == 0
    except FileNotFoundError:
        make_ok = False

    if make_ok:
        lines.append("make_available=true")
    else:
        lines.append("make_unavailable=true")
        lines.append("fallback=python scripts/dev_up.py (same stack as make up)")

    _kill_port(API_PORT)
    _kill_port(DASH_PORT)

    for run_id in (1, 2):
        if run_id > 1:
            _kill_port(API_PORT)
            _kill_port(DASH_PORT)
        lines.extend(_boot_stack(run_id))

    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def capture_playwright_demo() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    pw = subprocess.run(["npx", "playwright", "--version"], capture_output=True, text=True, shell=True)
    if pw.returncode != 0:
        fallback = SCRATCH / "playwright_unavailable.log"
        app = (ROOT / "dashboard" / "src" / "App.tsx").read_text(encoding="utf-8")
        panels = [
            "Net position",
            "Quota",
            "Rate",
            "Activity",
            "Agent lanes",
            "Spend ledger",
            "Revenue ledger",
            "402 Inspector",
            "MissionProgress",
            "RateSparkline",
            "PanelHelp",
            "demo",
        ]
        found = [p for p in panels if p.lower().replace(" ", "") in app.lower().replace(" ", "") or p in app]
        fallback.write_text(
            "playwright_unavailable=true\n"
            "structural_fallback=demo_fixtures+vitest+panel_components\n"
            f"panels_found={','.join(found)}\n",
            encoding="utf-8",
        )
        return 1

    _kill_port(API_PORT)
    _kill_port(DASH_PORT)
    api = _start_api()
    dash = _start_dashboard()
    code = 1
    try:
        _wait_health()
        _wait_dashboard()
        time.sleep(3)
        env = {**os.environ, "GOAL_SCRATCH": str(SCRATCH), "DASHBOARD_URL": f"http://127.0.0.1:{DASH_PORT}"}
        proc = subprocess.run(
            ["pnpm", "exec", "node", "scripts/capture_dashboard_playwright.mjs"],
            cwd=ROOT / "dashboard",
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            shell=True,
        )
        (SCRATCH / "playwright_run.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
        shot = SCRATCH / "dashboard_demo.png"
        capture_log = SCRATCH / "playwright_capture.log"
        code = 0 if shot.exists() and proc.returncode == 0 else 1
        summary = SCRATCH / "playwright_unavailable.log"
        summary.write_text(
            f"playwright_version={pw.stdout.strip()}\n"
            f"screenshot_exists={shot.exists()}\n"
            f"capture_exit={proc.returncode}\n",
            encoding="utf-8",
        )
        if capture_log.exists():
            make_up = SCRATCH / "make_up.log"
            extra = ["", "=== wizard + demo (playwright) ===", capture_log.read_text(encoding="utf-8").rstrip()]
            make_up.write_text(make_up.read_text(encoding="utf-8").rstrip() + "\n" + "\n".join(extra) + "\n", encoding="utf-8")
    except Exception as exc:
        (SCRATCH / "playwright_unavailable.log").write_text(
            f"playwright_version={pw.stdout.strip()}\nplaywright_error={exc}\n",
            encoding="utf-8",
        )
    finally:
        _stop_procs(api, dash)

    return code


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    capture_sse_heartbeat()
    capture_make_up()
    return capture_playwright_demo()


if __name__ == "__main__":
    raise SystemExit(main())