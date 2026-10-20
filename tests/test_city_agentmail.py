"""AgentMail (MailRail) hooks for US City Network calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import mcp_server
from app.city_compliance import agentmail, mcp_tools as city_mcp
from app.city_compliance import registry
from app.config import settings
from app.mailrail import _SEEN_KEYS
from app.main import app


@pytest.fixture
def mail_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ledger = tmp_path / "mailrail.jsonl"
    monkeypatch.setattr("app.mailrail.MAILRAIL_LEDGER_FILE", ledger)
    monkeypatch.setattr(settings, "mailrail_admin_recipient", "ops@x402.test")
    _SEEN_KEYS.clear()
    return ledger


def _ledger_records(ledger: Path) -> list[dict[str, Any]]:
    if not ledger.exists():
        return []
    return [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_format_city_call_alert_includes_city_context() -> None:
    subject, body = agentmail.format_city_call_alert(
        "paid_settle",
        city_code="sea",
        city_name="Seattle",
        state="WA",
        address="400 Pine St",
        channel="http",
        price="$0.01",
        verdict="licensed_clean",
        paid=True,
        tx_hash="0xabc",
    )
    assert "paid_settle" in subject
    assert "Seattle" in subject
    assert "sea" in body
    assert "licensed_clean" in body
    assert "0xabc" in body


def test_two_catalog_calls_both_dispatch(mail_ledger: Path) -> None:
    """Each catalog browse must emit its own AgentMail (no process-lifetime dedup)."""
    res1 = agentmail.notify_city_call("catalog", channel="http", detail="first")
    res2 = agentmail.notify_city_call("catalog", channel="http", detail="second")
    assert res1 is not None and res1["status"] == "sent"
    assert res2 is not None and res2["status"] == "sent"
    records = _ledger_records(mail_ledger)
    assert len(records) == 2
    assert records[0]["event_id"] != records[1]["event_id"]


@pytest.mark.asyncio
async def test_two_sample_calls_both_dispatch(
    mail_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each sample call must emit its own AgentMail even for the same city."""

    async def fake_check(address: str) -> dict[str, Any]:
        return {"address": address, "compliance_verdict": "sample_ok"}

    monkeypatch.setattr(registry.get_city("mn"), "check_property", fake_check)
    await city_mcp.get_us_city_property_sample("mn", agent_id="sample-agent")
    await city_mcp.get_us_city_property_sample("mn", agent_id="sample-agent")
    records = _ledger_records(mail_ledger)
    assert len(records) == 2
    assert all(r["metadata"]["call_kind"] == "sample" for r in records)
    assert records[0]["event_id"] != records[1]["event_id"]


def test_paid_tx_hash_retries_deduplicate(mail_ledger: Path) -> None:
    """True retries of the same settled payment share one event_id."""
    kwargs = {
        "call_kind": "paid_settle",
        "city_code": "sea",
        "channel": "http",
        "address": "400 Pine St",
        "tx_hash": "0xabc123",
        "paid": True,
    }
    res1 = agentmail.notify_city_call(**kwargs)
    res2 = agentmail.notify_city_call(**kwargs)
    assert res1 is not None and res1["status"] == "sent"
    assert res2 is not None and res2["status"] == "deduplicated"
    assert len(_ledger_records(mail_ledger)) == 1


def test_request_id_retries_deduplicate(mail_ledger: Path) -> None:
    """Explicit request_id enables stable dedup without a tx hash."""
    res1 = agentmail.notify_city_call(
        "paid_probe",
        city_code="nyc",
        channel="mcp",
        address="1 Centre St",
        request_id="probe-handoff-42",
    )
    res2 = agentmail.notify_city_call(
        "paid_probe",
        city_code="nyc",
        channel="mcp",
        address="1 Centre St",
        request_id="probe-handoff-42",
    )
    assert res1 is not None and res1["status"] == "sent"
    assert res2 is not None and res2["status"] == "deduplicated"
    assert len(_ledger_records(mail_ledger)) == 1


def test_notify_city_call_records_ledger(mail_ledger: Path) -> None:
    res = agentmail.notify_city_call(
        "catalog",
        channel="mcp",
        agent_id="test-agent",
        detail="city_count=14",
    )
    assert res is not None
    assert res["status"] == "sent"
    records = _ledger_records(mail_ledger)
    assert len(records) == 1
    assert records[0]["metadata"]["call_kind"] == "catalog"
    assert records[0]["to"] == "ops@x402.test"


@pytest.mark.asyncio
async def test_mcp_list_us_cities_sends_agentmail(mail_ledger: Path) -> None:
    await city_mcp.list_us_cities(agent_id="catalog-agent")
    records = _ledger_records(mail_ledger)
    assert len(records) == 1
    assert records[0]["metadata"]["call_kind"] == "catalog"
    assert records[0]["metadata"]["channel"] == "mcp"


@pytest.mark.asyncio
async def test_mcp_sample_sends_per_city_agentmail(
    mail_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_check(address: str) -> dict[str, Any]:
        return {"address": address, "compliance_verdict": "sample_ok"}

    monkeypatch.setattr(registry.get_city("mn"), "check_property", fake_check)
    await city_mcp.get_us_city_property_sample("mn", agent_id="sample-agent")
    records = _ledger_records(mail_ledger)
    assert len(records) == 1
    assert records[0]["metadata"]["call_kind"] == "sample"
    assert records[0]["metadata"]["city_code"] == "mn"


@pytest.mark.asyncio
async def test_mcp_check_probe_sends_agentmail(
    mail_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "evm_private_key", None)

    async def fake_probe(params):  # noqa: ANN001
        return {"status_code": 402, "url": str(params.url)}

    monkeypatch.setattr(city_mcp.x402_services, "get_payment_requirements", fake_probe)
    await city_mcp.check_us_city_property(
        "nyc", "1 Centre St", agent_id="probe-agent"
    )
    records = _ledger_records(mail_ledger)
    assert len(records) == 1
    assert records[0]["metadata"]["call_kind"] == "paid_probe"
    assert records[0]["metadata"]["city_code"] == "nyc"


@pytest.mark.asyncio
async def test_mcp_check_paid_sends_agentmail(
    mail_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "evm_private_key", "0x" + "ab" * 32)

    async def fake_pay(params):  # noqa: ANN001
        return {
            "status_code": 200,
            "url": str(params.url),
            "body": json.dumps({"compliance_verdict": "licensed_clean"}),
            "payment_settled": True,
            "payment_settlement": {
                "success": True,
                "transaction": "0xpaidtx",
                "payer": "0xpayer",
            },
            "sdk": "mock",
        }

    monkeypatch.setattr(city_mcp.x402_services, "pay_and_fetch", fake_pay)
    await city_mcp.check_us_city_property(
        "chi", "121 N LaSalle St", agent_id="paid-agent"
    )
    records = _ledger_records(mail_ledger)
    assert len(records) == 1
    assert records[0]["metadata"]["call_kind"] == "paid_mcp"
    assert "licensed_clean" in records[0]["body"]


@pytest.mark.asyncio
async def test_mcp_wrapper_passes_resolved_agent_id(
    mail_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await mcp_server.list_us_cities(agent_id="wrapper-agent")
    records = _ledger_records(mail_ledger)
    assert records[0]["metadata"]["agent_id"] == "wrapper-agent"


def test_http_unpaid_402_does_not_send_agentmail(
    mail_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.city_compliance import gate

    monkeypatch.setattr(settings, "x402_pay_to_address", "0x" + "ab" * 20)
    monkeypatch.setattr(gate, "build_payment_required_header", lambda *a, **k: "pr")
    client = TestClient(app)
    res = client.get("/us/sea/property-check", params={"address": "400 Pine St"})
    assert res.status_code == 402
    assert res.json()["error"] == "payment_required"
    assert _ledger_records(mail_ledger) == []


def test_http_us_cities_catalog_sends_agentmail(mail_ledger: Path) -> None:
    client = TestClient(app)
    res = client.get("/us/cities")
    assert res.status_code == 200
    records = _ledger_records(mail_ledger)
    assert len(records) == 1
    assert records[0]["metadata"]["call_kind"] == "catalog"
    assert records[0]["metadata"]["channel"] == "http"


def test_http_mn_sample_upstream_failure_sends_agentmail(
    mail_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import mn_compliance

    async def boom(address: str) -> dict[str, Any]:
        raise TimeoutError("upstream down")

    monkeypatch.setattr(mn_compliance, "check_property", boom)
    client = TestClient(app)
    res = client.get("/mn/property-check/sample")
    assert res.status_code == 502
    assert res.json()["error"] == "upstream_open_data_unavailable"
    records = _ledger_records(mail_ledger)
    assert len(records) == 1
    assert records[0]["metadata"]["call_kind"] == "error"
    assert records[0]["metadata"]["city_code"] == "mn"
    assert records[0]["metadata"]["channel"] == "http"
    assert "upstream_open_data_unavailable" in records[0]["body"]


def test_http_city_sample_sends_agentmail(
    mail_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_check(address: str) -> dict[str, Any]:
        return {"address": address, "compliance_verdict": "licensed_clean"}

    monkeypatch.setattr(registry.get_city("sea"), "check_property", fake_check)
    client = TestClient(app)
    res = client.get("/us/sea/property-check/sample")
    assert res.status_code == 200
    records = _ledger_records(mail_ledger)
    assert len(records) == 1
    assert records[0]["metadata"]["call_kind"] == "sample"
    assert records[0]["metadata"]["city_code"] == "sea"


def test_notify_city_call_never_raises(
    mail_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a, **_k):  # noqa: ANN002, ANN003
        raise RuntimeError("mail down")

    monkeypatch.setattr(agentmail.mailrail, "send_agent_mail", boom)
    assert agentmail.notify_city_call("catalog", channel="http") is None


def test_http_paid_upstream_failure_sends_agentmail(
    mail_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.city_compliance import gate

    test_pay_to = "0xTestPayTo00000000000000000000000000000002"
    monkeypatch.setattr(settings, "x402_pay_to_address", test_pay_to)

    async def fake_settle(signature: str, payment_required: str) -> dict:
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {
                "success": True,
                "transaction": "0xdeadbeef",
                "payer": "0xpayer123",
            },
            "invalid_reason": None,
            "settlement_error": None,
        }

    async def boom(address: str) -> dict[str, Any]:
        raise TimeoutError("upstream down")

    monkeypatch.setattr(gate, "verify_and_settle", fake_settle)
    monkeypatch.setattr(registry.get_city("sea"), "check_property", boom)
    client = TestClient(app)
    res = client.get(
        "/us/sea/property-check",
        params={"address": "400 Pine St"},
        headers={"PAYMENT-SIGNATURE": "sig-paid"},
    )
    assert res.status_code == 502
    assert res.json()["error"] == "upstream_open_data_unavailable"
    assert res.headers.get("payment-response")
    records = _ledger_records(mail_ledger)
    assert len(records) == 1
    assert records[0]["metadata"]["call_kind"] == "error"
    assert records[0]["metadata"]["city_code"] == "sea"
    assert records[0]["metadata"]["channel"] == "http"
    assert "(paid)" in records[0]["subject"]
    assert "0xdeadbeef" in records[0]["body"]
    assert "upstream_open_data_unavailable" in records[0]["body"]


def test_http_property_due_diligence_upstream_failure_sends_agentmail(
    mail_ledger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import property_due_diligence_agent as diligence_agent

    monkeypatch.setattr(settings, "x402_pay_to_address", "0x" + "ab" * 20)

    async def fake_settle(signature: str, payment_required: str) -> dict:
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {
                "success": True,
                "transaction": "0xfeedface",
                "payer": "0xbuyer456",
            },
        }

    async def boom(city_code: str, address: str) -> dict[str, Any]:
        raise TimeoutError("upstream down")

    monkeypatch.setattr(diligence_agent, "verify_and_settle", fake_settle)
    monkeypatch.setattr(diligence_agent, "run_check", boom)
    client = TestClient(app)
    res = client.get(
        "/agent/property-due-diligence",
        params={"city_code": "mn", "address": "1700 Penn Ave N"},
        headers={"PAYMENT-SIGNATURE": "sig-paid"},
    )
    assert res.status_code == 502
    assert res.json()["error"] == "upstream_open_data_unavailable"
    assert res.headers.get("payment-response")
    records = _ledger_records(mail_ledger)
    assert len(records) == 1
    assert records[0]["metadata"]["call_kind"] == "error"
    assert records[0]["metadata"]["city_code"] == "mn"
    assert "(paid)" in records[0]["subject"]
    assert "0xfeedface" in records[0]["body"]
    assert "upstream_open_data_unavailable" in records[0]["body"]
