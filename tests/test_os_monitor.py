"""Host OS monitoring — snapshot shape, verdict thresholds, history, alerts, HTTP."""

from fastapi.testclient import TestClient

from app import ops_events, os_monitor
from app.main import app
from app.tools_registry import EXPECTED_TOOL_NAMES


client = TestClient(app)


def test_snapshot_shape() -> None:
    snap = os_monitor.sample()
    assert snap["status"] in ("ok", "warn", "critical")
    assert isinstance(snap["concerns"], list)
    assert 0.0 <= snap["cpu"]["percent"] <= 100.0
    assert snap["cpu"]["cores_logical"] >= 1
    assert 0.0 <= snap["memory"]["percent"] <= 100.0
    assert snap["memory"]["total_mb"] > 0
    assert 0.0 <= snap["disk"]["percent"] <= 100.0
    assert snap["disk"]["total_gb"] > 0
    assert snap["system"]["process_count"] > 0
    assert snap["system"]["uptime_seconds"] >= 0
    assert snap["ts"]


def test_verdict_thresholds() -> None:
    status, concerns = os_monitor._verdict(10.0, 10.0, 10.0)
    assert status == "ok" and concerns == []

    status, concerns = os_monitor._verdict(80.0, 10.0, 10.0)
    assert status == "warn"
    assert any("cpu" in c for c in concerns)

    status, concerns = os_monitor._verdict(10.0, 95.0, 10.0)
    assert status == "critical"
    assert any("memory" in c for c in concerns)

    # Worst level wins across resources.
    status, concerns = os_monitor._verdict(80.0, 95.0, 87.0)
    assert status == "critical"
    assert len(concerns) == 3


def test_history_accumulates_and_limits() -> None:
    before = len(os_monitor.get_history(720))
    os_monitor.sample()
    os_monitor.sample()
    history = os_monitor.get_history(720)
    assert len(history) == min(before + 2, 720)
    assert len(os_monitor.get_history(1)) == 1
    # Most recent sample is last (oldest first).
    assert history[-1]["ts"] >= history[0]["ts"]


def test_alert_emitted_on_level_transition(monkeypatch) -> None:
    monkeypatch.setattr(os_monitor, "_last_status", "ok")
    monkeypatch.setattr(
        os_monitor, "_verdict", lambda *a: ("critical", ["cpu at 99.0% (critical)"])
    )
    os_monitor.sample()
    events = [
        e
        for e in ops_events.recent_events(50)
        if e.get("meta", {}).get("os_alert")
    ]
    assert events, "expected an os_alert event on ok -> critical transition"
    latest = events[-1]
    assert latest["meta"]["status"] == "critical"
    assert latest["meta"]["previous"] == "ok"

    # No duplicate alert while the level is unchanged.
    count_before = len(events)
    os_monitor.sample()
    events_after = [
        e
        for e in ops_events.recent_events(50)
        if e.get("meta", {}).get("os_alert")
    ]
    assert len(events_after) == count_before


def test_top_processes() -> None:
    rows = os_monitor._top_processes(3)
    assert 1 <= len(rows) <= 3
    assert rows[0]["rss_mb"] >= rows[-1]["rss_mb"]
    assert all("pid" in r and "name" in r for r in rows)


def test_http_os_snapshot() -> None:
    response = client.get("/os")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "warn", "critical")
    assert "top_processes" not in body


def test_http_os_snapshot_with_processes() -> None:
    response = client.get("/os", params={"processes": "true"})
    assert response.status_code == 200
    assert response.json()["top_processes"]


def test_http_os_history() -> None:
    client.get("/os")  # ensure at least one sample exists
    response = client.get("/os/history", params={"limit": 5})
    assert response.status_code == 200
    samples = response.json()["samples"]
    assert 1 <= len(samples) <= 5


def test_tool_registered() -> None:
    assert "get_os_metrics" in EXPECTED_TOOL_NAMES
