"""Doctor CLI and GET /doctor checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.doctor import run_checks
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_doctor_http_returns_checks() -> None:
    response = client.get("/doctor")
    assert response.status_code == 200
    body = response.json()
    assert "checks" in body
    assert "summary" in body
    ids = {c["id"] for c in body["checks"]}
    assert "pay_to" in ids
    assert "facilitator" in ids
    assert "network" in ids


def test_doctor_config_echo() -> None:
    report = run_checks()
    assert "has_pay_to" in report["config"]
    assert "redis_mode" in report["config"]
    assert report["config"]["redis_mode"] in ("memory", "redis")


def test_doctor_cli_runs() -> None:
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)
    proc = subprocess.run(
        [str(python), "-m", "app.doctor"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert "Doctor" in proc.stdout
    assert "PASS" in proc.stdout or "FAIL" in proc.stdout or "WARN" in proc.stdout