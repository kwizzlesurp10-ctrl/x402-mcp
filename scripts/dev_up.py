"""Start FastAPI + dashboard with prefixed logs (make up)."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


def main() -> int:
    api = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8402"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    dash = subprocess.Popen(
        ["pnpm", "dev"],
        cwd=ROOT / "dashboard",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=True,
    )

    # One pump thread per child: a single alternating readline loop stalls on
    # whichever child is quiet, stops draining the other pipe, and freezes that
    # child once its 64KB stdout buffer fills (uvicorn blocks mid-log write).
    def _pump(proc: subprocess.Popen, prefix: str) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(f"[{prefix}] {line}", end="", flush=True)

    threads = [
        threading.Thread(target=_pump, args=(api, "api"), daemon=True),
        threading.Thread(target=_pump, args=(dash, "dash"), daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        api.wait()
        dash.wait()
    except KeyboardInterrupt:
        api.terminate()
        dash.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())