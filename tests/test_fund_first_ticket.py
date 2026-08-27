"""Fund-First Settle Ticket — payTo settles before any paid payload."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import diligence_pack, fund_first_ticket
from app.config import settings
from app.main import app
from app.x402_services import resolve_revenue_network

PRODUCT_ID = "fund-first-ticket"
TEST_PAY_TO = "0xAB745e5F576667037696e78ba7dA28E193E4423D"
MAINNET_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "x402_pay_to_address", TEST_PAY_TO)
    monkeypatch.setattr(settings, "fund_first_ticket_price", "$0.05")
    monkeypatch.setattr(settings, "public_base_url", "http://test")
    fund_first_ticket.reset_grants_for_tests()
    return TestClient(app)


@pytest.fixture
def mock_challenge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fund_first_ticket, "build_payment_required_header", lambda: "dGVzdA=="
    )


def test_price_lives_only_in_config() -> None:
    assert settings.fund_first_ticket_price == "$0.05"
    assert fund_first_ticket.PRODUCT_ID == PRODUCT_ID
    assert fund_first_ticket.price_string() == "$0.05"
    assert fund_first_ticket.amount_usdc() == 0.05


def test_sample_is_free_and_does_not_settle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def must_not_settle(*_a, **_k):  # noqa: ANN001
        raise AssertionError("sample must never settle")

    monkeypatch.setattr(fund_first_ticket, "verify_and_settle", must_not_settle)
    r = client.get("/pay/ticket/sample")
    assert r.status_code == 200
    body = r.json()
    assert body["sample"] is True
    assert body["product_id"] == PRODUCT_ID
    assert body["price"] == settings.fund_first_ticket_price
    assert body["paid_url"].endswith("/pay/ticket")
    assert "/us/" in body["city_sample_url"] and body["city_sample_url"].endswith(
        "/property-check/sample"
    )
    assert body["diligence_url"].endswith("/tasks/us-rental-diligence")
    assert "grant" not in body or body.get("grant") in (None, "")


def test_unpaid_get_is_402_not_422(
    client: TestClient, mock_challenge: None
) -> None:
    r = client.get("/pay/ticket")
    assert r.status_code == 402
    assert r.headers.get("payment-required") == "dGVzdA=="
    body = r.json()
    assert body["error"] == "payment_required"
    assert body["product_id"] == PRODUCT_ID
    assert body["price"] == "$0.05"
    assert body["pay_to"] == TEST_PAY_TO


def test_missing_pay_to_is_503_not_422(
    monkeypatch: pytest.MonkeyPatch, mock_challenge: None
) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", None)
    r = TestClient(app).get("/pay/ticket")
    assert r.status_code == 503
    assert r.json()["error"] == "seller_not_configured"


def test_paid_payload_is_not_built_before_settle(
    client: TestClient, mock_challenge: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[str] = []

    def trap_ticket(*_a, **_k):  # noqa: ANN001
        built.append("ticket")
        raise AssertionError("ticket must not be signed before settle")

    monkeypatch.setattr(fund_first_ticket, "issue_settled_ticket", trap_ticket)

    async def reject(_sig: str, _pr: str) -> dict:
        return {
            "is_valid": False,
            "payment_settled": False,
            "invalid_reason": "nope",
        }

    monkeypatch.setattr(fund_first_ticket, "verify_and_settle", reject)
    r = client.get("/pay/ticket", headers={"PAYMENT-SIGNATURE": "sig"})
    assert r.status_code == 402
    assert built == []
    assert r.json()["error"] == "payment_rejected"


def test_paid_get_returns_ticket_after_settle(
    client: TestClient, mock_challenge: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_settle(_sig: str, _pr: str) -> dict:
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {
                "success": True,
                "transaction": "0xabc",
                "payer": "0xbuyer",
                "network": "eip155:8453",
            },
        }

    monkeypatch.setattr(fund_first_ticket, "verify_and_settle", fake_settle)
    rev: list[dict] = []
    monkeypatch.setattr(
        "app.swarm.ledger_writer.record_revenue",
        lambda **kwargs: rev.append(kwargs) or kwargs,
    )

    r = client.get("/pay/ticket", headers={"PAYMENT-SIGNATURE": "sig"})
    assert r.status_code == 200, r.text
    body = r.json()
    for key in (
        "ticket_id",
        "product_id",
        "pay_to",
        "network",
        "asset",
        "amount_usdc",
        "tx",
        "payer",
        "settled_at",
        "grant",
    ):
        assert key in body, key
    assert body["product_id"] == PRODUCT_ID
    assert body["pay_to"] == TEST_PAY_TO
    assert body["asset"] == MAINNET_USDC
    assert body["amount_usdc"] == 0.05
    assert body["tx"] == "0xabc"
    assert body["payer"] == "0xbuyer"
    assert body["grant"]
    assert rev and rev[0]["product_id"] == PRODUCT_ID
    assert rev[0]["amount_usdc"] == 0.05
    assert r.headers.get("payment-response")


def test_failed_settle_does_not_write_revenue(
    client: TestClient, mock_challenge: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_settle(_sig: str, _pr: str) -> dict:
        return {
            "is_valid": True,
            "payment_settled": False,
            "settlement": {"success": False},
            "settlement_error": "pending",
        }

    monkeypatch.setattr(fund_first_ticket, "verify_and_settle", fake_settle)
    rev: list[dict] = []
    monkeypatch.setattr(
        "app.swarm.ledger_writer.record_revenue",
        lambda **kwargs: rev.append(kwargs) or kwargs,
    )
    r = client.get("/pay/ticket", headers={"PAYMENT-SIGNATURE": "sig"})
    assert r.status_code == 402
    assert rev == []


def test_cdp_creds_sell_base_mainnet_not_sepolia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "revenue_network", None)
    monkeypatch.setattr(settings, "cdp_api_key_id", "id")
    monkeypatch.setattr(settings, "cdp_api_key_secret", "secret")
    monkeypatch.setattr(settings, "cdp_networks", "eip155:8453")
    monkeypatch.setattr(settings, "x402_default_network", "eip155:84532")
    assert resolve_revenue_network() == "eip155:8453"
    assert fund_first_ticket.sell_network() == "eip155:8453"
    assert fund_first_ticket.sell_asset() == MAINNET_USDC


def test_grant_is_one_use_on_diligence_pack(
    client: TestClient, mock_challenge: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_settle(_sig: str, _pr: str) -> dict:
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {
                "success": True,
                "transaction": "0xdef",
                "payer": "0xbuyer",
            },
        }

    monkeypatch.setattr(fund_first_ticket, "verify_and_settle", fake_settle)
    monkeypatch.setattr(
        "app.swarm.ledger_writer.record_revenue", lambda **kwargs: kwargs
    )
    paid = client.get("/pay/ticket", headers={"PAYMENT-SIGNATURE": "sig"})
    grant = paid.json()["grant"]

    async def must_not_settle(*_a, **_k):  # noqa: ANN001
        raise AssertionError("grant path must not settle diligence USDC")

    monkeypatch.setattr(diligence_pack, "build_payment_required_header", lambda: "dGVzdA==")
    monkeypatch.setattr(diligence_pack, "verify_and_settle", must_not_settle)

    async def fake_check(city: str, address: str) -> dict:
        return {
            "city_code": city,
            "address": address,
            "ok": True,
            "compliance_verdict": "licensed_clean",
            "bucket": "clean",
            "report": {"compliance_verdict": "licensed_clean"},
        }

    monkeypatch.setattr(diligence_pack, "check_one", fake_check)

    body = {
        "properties": [{"city_code": "mn", "address": "1700 Penn Ave N"}],
        "idempotency_key": "grant-once",
    }
    first = client.post(
        "/tasks/us-rental-diligence",
        headers={"X-FUND-FIRST-TICKET": grant},
        json=body,
    )
    assert first.status_code == 200, first.text
    assert first.json()["payment_settled"] is True

    second = client.post(
        "/tasks/us-rental-diligence",
        headers={"X-FUND-FIRST-TICKET": grant},
        json=body,
    )
    assert second.status_code == 402
    assert second.json()["error"] in {"payment_required", "payment_rejected"}


def test_bad_diligence_body_does_not_burn_grant(
    client: TestClient, mock_challenge: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_settle(_sig: str, _pr: str) -> dict:
        return {
            "is_valid": True,
            "payment_settled": True,
            "settlement": {"success": True, "transaction": "0x1", "payer": "0x2"},
        }

    monkeypatch.setattr(fund_first_ticket, "verify_and_settle", fake_settle)
    monkeypatch.setattr(
        "app.swarm.ledger_writer.record_revenue", lambda **kwargs: kwargs
    )
    grant = client.get("/pay/ticket", headers={"PAYMENT-SIGNATURE": "sig"}).json()[
        "grant"
    ]
    monkeypatch.setattr(diligence_pack, "build_payment_required_header", lambda: "dGVzdA==")

    bad = client.post(
        "/tasks/us-rental-diligence",
        headers={"X-FUND-FIRST-TICKET": grant},
        json={"properties": []},
    )
    assert bad.status_code == 422

    async def fake_check(city: str, address: str) -> dict:
        return {
            "city_code": city,
            "address": address,
            "ok": True,
            "compliance_verdict": "licensed_clean",
            "bucket": "clean",
            "report": {"compliance_verdict": "licensed_clean"},
        }

    monkeypatch.setattr(diligence_pack, "check_one", fake_check)
    ok = client.post(
        "/tasks/us-rental-diligence",
        headers={"X-FUND-FIRST-TICKET": grant},
        json={"properties": [{"city_code": "mn", "address": "1700 Penn Ave N"}]},
    )
    assert ok.status_code == 200, ok.text


def test_agent_surface_lists_ticket() -> None:
    from app import agent_surface

    urls = [r["url"] for r in agent_surface.paid_resources()]
    assert any(u.endswith("/pay/ticket") for u in urls)
    assert any(u.endswith("/pay/ticket/sample") for u in urls)
    paid = next(r for r in agent_surface.paid_resources() if r["url"].endswith("/pay/ticket"))
    assert paid["price"] == settings.fund_first_ticket_price
    assert paid["product_id"] == PRODUCT_ID
