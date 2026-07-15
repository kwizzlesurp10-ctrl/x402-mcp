"""Start FastAPI + dashboard with prefixed logs (make up)."""

from __future__ import annotations

import subprocess
import sys
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

    try:
        while True:
            if api.poll() is not None and dash.poll() is not None:
                break
            if api.stdout:
                line = api.stdout.readline()
                if line:
                    print(f"[api] {line}", end="")
            if dash.stdout:
                line = dash.stdout.readline()
                if line:
                    print(f"[dash] {line}", end="")
    except KeyboardInterrupt:
        api.terminate()
        dash.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())