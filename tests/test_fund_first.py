"""Fund-First Settle Ticket — hermetic tests (no live USDC)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import demand, fund_first, ledger_io, x402_middleware_pilot
from app.config import settings
from app.main import app
from app.x402_services import resolve_revenue_network

PRODUCT_ID = "fund-first-ticket"
PAID = "/pay/ticket"
SAMPLE = "/pay/ticket/sample"
MAINNET_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TEST_PAY_TO = "0xAB745e5F576667037696e78ba7dA28E193E4423D"

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_demand(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import redis_client

    monkeypatch.setattr(demand, "_memory", demand.Counter())
    monkeypatch.setattr(demand, "_memory_last", {})
    monkeypatch.setattr(demand, "_memory_clients", {})
    monkeypatch.setattr(demand, "_memory_ua", {})
    monkeypatch.setattr(redis_client, "client", None)
    fund_first.reset_grants_for_tests()


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    d = tmp_path / "ledger"
    d.mkdir()
    monkeypatch.setattr(ledger_io, "LEDGER", d)
    return d


def _settle_ctx(
    *,
    path: str = PAID,
    success: bool = True,
    settled_amount: str | None = None,
    required_amount: str = "50000",
    network: str = "eip155:8453",
    payer: str = "0xBUYER",
    tx: str = "0xdeadbeef",
):
    return SimpleNamespace(
        result=SimpleNamespace(
            success=success,
            amount=settled_amount,
            network=network,
            payer=payer,
            transaction=tx,
        ),
        requirements=SimpleNamespace(
            amount=required_amount,
            network=network,
            asset=MAINNET_USDC,
        ),
        transport_context=SimpleNamespace(request=SimpleNamespace(path=path)),
    )


def test_product_id_spelling_lock() -> None:
    assert fund_first.PRODUCT_ID == PRODUCT_ID
    assert x402_middleware_pilot.PRODUCT_IDS[PAID] == PRODUCT_ID
    assert settings.fund_first_ticket_price == "$0.05"


def test_sample_is_200_and_never_settles() -> None:
    r = client.get(SAMPLE)
    assert r.status_code == 200
    body = r.json()
    assert body["sample"] is True
    assert body["product_id"] == PRODUCT_ID
    assert body["price"] == settings.fund_first_ticket_price
    assert body["payTo_field"] == "payTo"
    assert "PAYMENT-SIGNATURE" in body["how_to_pay"]
    assert body["paid_url"].endswith(PAID)


def test_sample_unconfigured_still_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", None)
    a = FastAPI()
    a.include_router(fund_first.sample_router)
    r = TestClient(a).get(SAMPLE)
    assert r.status_code == 200
    assert r.json()["seller_unconfigured"] is True
    assert r.json()["product_id"] == PRODUCT_ID


def test_unconfigured_does_not_register_paid_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", None)
    a = FastAPI()
    x402_middleware_pilot.register(a)
    a.include_router(fund_first.sample_router)
    c = TestClient(a)
    assert c.get(PAID).status_code == 404
    assert c.get(SAMPLE).status_code == 200


def test_unpaid_402_contains_pay_to() -> None:
    r = client.get(PAID)
    assert r.status_code == 402
    assert "payment-required" in r.headers
    import base64
    import json

    decoded = json.loads(base64.b64decode(r.headers["payment-required"]))
    accept = decoded["accepts"][0]
    assert accept["scheme"] == "exact"
    assert accept["payTo"].lower() == settings.x402_pay_to_address.lower()
    assert accept["amount"] == "50000"
    assert accept["network"] == resolve_revenue_network()


def test_unsigned_402_records_demand_under_exact_product_id() -> None:
    client.get(PAID)
    assert demand.challenges().get(PRODUCT_ID) == 1


def test_self_traffic_header_ignored() -> None:
    client.get(PAID, headers={"x-demand-ignore": "1"})
    assert demand.challenges() == {}


def test_signature_402_is_not_a_view() -> None:
    client.get(PAID, headers={"PAYMENT-SIGNATURE": "garbage"})
    assert demand.challenges() == {}


def test_settled_payment_writes_revenue_mock(ledger) -> None:
    x402_middleware_pilot._record_settled_revenue(_settle_ctx())
    rows = list(ledger_io.read_ledger_rows("revenue", limit=None))
    assert len(rows) == 1
    row = rows[0]
    assert row["product_id"] == PRODUCT_ID
    assert row["amount_usdc"] == 0.05
    assert row["payer"] == "0xbuyer"
    assert row["tx"] == "0xdeadbeef"
    assert row["settled"] is True


def test_failed_settle_writes_nothing(ledger) -> None:
    x402_middleware_pilot._record_settled_revenue(_settle_ctx(success=False))
    assert list(ledger_io.read_ledger_rows("revenue", limit=None)) == []


def test_listed_price_is_last_resort_amount(ledger) -> None:
    x402_middleware_pilot._record_settled_revenue(
        _settle_ctx(settled_amount=None, required_amount="not-a-number")
    )
    assert list(ledger_io.read_ledger_rows("revenue", limit=None))[0]["amount_usdc"] == 0.05


@pytest.mark.asyncio
async def test_handler_emits_ticket_only_after_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)
    fund_first.capture_settlement(
        tx="0xabc",
        payer="0xbuyer",
        network="eip155:8453",
        amount_usdc=0.05,
        asset=MAINNET_USDC,
    )
    resp = await fund_first.fund_first_paid()
    assert resp.status_code == 200
    body = resp.body
    import json

    ticket = json.loads(body)
    for key in (
        "ok",
        "product_id",
        "pay_to",
        "network",
        "asset",
        "amount_usdc",
        "tx",
        "payer",
        "ticket_id",
        "grant",
        "unlocks",
        "settled_at",
    ):
        assert key in ticket, key
    assert ticket["ok"] is True
    assert ticket["product_id"] == PRODUCT_ID
    assert ticket["pay_to"] == TEST_PAY_TO
    assert ticket["network"] == "eip155:8453"
    assert ticket["asset"] == MAINNET_USDC
    assert ticket["amount_usdc"] == 0.05
    assert ticket["unlocks"] == "POST /tasks/us-rental-diligence"
    assert ticket["grant"]


@pytest.mark.asyncio
async def test_handler_without_capture_does_not_invent_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)
    fund_first.reset_grants_for_tests()
    resp = await fund_first.fund_first_paid()
    assert resp.status_code == 503


def test_cdp_creds_sell_base_mainnet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "revenue_network", None)
    monkeypatch.setattr(settings, "cdp_api_key_id", "id")
    monkeypatch.setattr(settings, "cdp_api_key_secret", "secret")
    monkeypatch.setattr(settings, "cdp_networks", "eip155:8453")
    monkeypatch.setattr(settings, "x402_default_network", "eip155:84532")
    assert resolve_revenue_network() == "eip155:8453"
    assert fund_first.sell_network() == "eip155:8453"
    assert fund_first.sell_asset() == MAINNET_USDC


def test_agent_surface_lists_ticket() -> None:
    from app import agent_surface

    urls = [r["url"] for r in agent_surface.paid_resources()]
    assert any(u.endswith(PAID) for u in urls)
    assert any(u.endswith(SAMPLE) for u in urls)
    paid = next(r for r in agent_surface.paid_resources() if r["url"].endswith(PAID))
    assert paid["price"] == settings.fund_first_ticket_price
    assert paid.get("product_id") == PRODUCT_ID
