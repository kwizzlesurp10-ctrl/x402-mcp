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

def test_rpc_failover(monkeypatch) -> None:
    from app.config import settings
    from app.doctor import run_checks
    
    settings.base_rpc_url = "https://broken.rpc.com"
    
    # Mock _ping_rpc to fail for broken.rpc.com and pass for llamarpc
    def mock_ping_rpc(url, **kwargs):
        if url == "https://broken.rpc.com":
            return False, "HTTP 500"
        return True, "HTTP 200"
        
    monkeypatch.setattr("app.doctor._ping_rpc", mock_ping_rpc)
    
    report = run_checks()
    rpc_checks = [c for c in report["checks"] if c["id"] == "rpc"]
    assert len(rpc_checks) == 1
    assert rpc_checks[0]["status"] == "warn"
    assert "RPC failover triggered" in rpc_checks[0]["message"]
    assert settings.base_rpc_url == "https://base.llamarpc.com"

def test_spend_velocity_anomaly(monkeypatch) -> None:
    from app.ops_events import emit_swarm_step, _recent_spends
    _recent_spends.clear()
    
    alerts = []
    def mock_emit_os_alert(status, previous, concerns):
        alerts.append(concerns[0])
    monkeypatch.setattr("app.ops_events.emit_os_alert", mock_emit_os_alert)
    
    # Emit a series of spend events
    emit_swarm_step(run_id="1", role="treasurer", phase="buying", action="pay_and_fetch", detail={"amount_usdc": 1.0, "settled": True})
    assert len(alerts) == 0
    
    emit_swarm_step(run_id="1", role="treasurer", phase="buying", action="pay_and_fetch", detail={"amount_usdc": 1.5, "settled": True})
    assert len(alerts) == 1
    assert "Spend velocity anomaly" in alerts[0]


def test_doctor_mailrail_checks(monkeypatch) -> None:
    from app.config import settings
    from app.doctor import run_checks

    # Default disabled mock
    monkeypatch.setattr(settings, "mailrail_enabled", False)
    report = run_checks()
    mail_check = next(c for c in report["checks"] if c["id"] == "mailrail")
    assert mail_check["status"] == "pass"

    # Enabled with Resend valid
    monkeypatch.setattr(settings, "mailrail_enabled", True)
    monkeypatch.setattr(settings, "mailrail_provider", "resend")
    monkeypatch.setattr(settings, "mailrail_api_key", "re_test_valid_key")
    report = run_checks()
    mail_check = next(c for c in report["checks"] if c["id"] == "mailrail")
    assert mail_check["status"] == "pass"

    # Enabled with Resend missing key
    monkeypatch.setattr(settings, "mailrail_api_key", None)
    report = run_checks()
    mail_check = next(c for c in report["checks"] if c["id"] == "mailrail")
    assert mail_check["status"] == "fail"

