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


def test_http_us_cities_catalog_sends_agentmail(mail_ledger: Path) -> None:
    client = TestClient(app)
    res = client.get("/us/cities")
    assert res.status_code == 200
    records = _ledger_records(mail_ledger)
    assert len(records) == 1
    assert records[0]["metadata"]["call_kind"] == "catalog"
    assert records[0]["metadata"]["channel"] == "http"


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
