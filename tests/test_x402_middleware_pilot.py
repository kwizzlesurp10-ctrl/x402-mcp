"""Pilot of the x402 SDK's own FastAPI payment middleware (app/x402_middleware_pilot.py).

Purely additive — these tests pin that it works end to end AND that it does
not disturb any existing route.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import demand, ledger_io, x402_middleware_pilot
from app.config import settings
from app.main import app
from app.swarm import ledger_writer
from app.x402_services import primary_caip2_network

client = TestClient(app)


def test_unpaid_ping_returns_402_with_payment_required_header() -> None:
    response = client.get("/pilot/ping")
    assert response.status_code == 402
    assert "payment-required" in response.headers


def test_payment_required_header_matches_configured_price_and_pay_to() -> None:
    response = client.get("/pilot/ping")
    decoded = json.loads(base64.b64decode(response.headers["payment-required"]))
    accept = decoded["accepts"][0]
    assert accept["scheme"] == "exact"
    assert accept["network"] == primary_caip2_network(settings.x402_default_network)
    assert "," not in accept["network"]
    assert accept["payTo"].lower() == settings.x402_pay_to_address.lower()
    # $0.001 -> 1000 atomic units of 6-decimal USDC.
    assert accept["amount"] == "1000"


def test_existing_routes_are_unaffected() -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/.well-known/mcp").status_code == 200


VALID_TX = "0x" + "a" * 64


def test_unpaid_finality_check_returns_402_with_correct_price() -> None:
    response = client.get("/base/finality-check", params={"tx": VALID_TX})
    assert response.status_code == 402
    decoded = json.loads(base64.b64decode(response.headers["payment-required"]))
    accept = decoded["accepts"][0]
    assert accept["network"] == primary_caip2_network(settings.x402_default_network)
    assert "," not in accept["network"]
    assert accept["payTo"].lower() == settings.x402_pay_to_address.lower()
    # $0.01 -> 10000 atomic units of 6-decimal USDC.
    assert accept["amount"] == "10000"


def test_finality_check_402_carries_bazaar_discovery_extension() -> None:
    response = client.get("/base/finality-check", params={"tx": VALID_TX})
    decoded = json.loads(base64.b64decode(response.headers["payment-required"]))
    assert "bazaar" in decoded.get("extensions", {})


def test_malformed_tx_is_still_gated_before_route_validation_runs() -> None:
    """Payment gating happens at the ASGI layer, before FastAPI's own query
    validation -- an unpaid request with a bad `tx` still gets the 402
    challenge, not a 422. The 422-without-charge property is enforced later,
    inside call_next, once a payment has actually been verified."""
    response = client.get("/base/finality-check", params={"tx": "not-a-hash"})
    assert response.status_code == 402


def test_mn_property_check_still_uses_its_own_hand_rolled_path() -> None:
    """Guards the "own section, don't touch current code" boundary: the
    generic middleware must not intercept a route it wasn't given."""
    response = client.get("/mn/property-check", params={"address": "1 Test St"})
    assert response.status_code in (402, 503)
    if response.status_code == 402:
        # Still the hand-rolled challenge shape, not the generic middleware's.
        assert response.json()["error"] == "payment_required"


JOINED_PRODUCTION_NETWORKS = (
    "eip155:8453,solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp,eip155:42161"
)


def test_comma_joined_default_network_serves_atomic_402(monkeypatch) -> None:
    """Production sets X402_DEFAULT_NETWORK to several rails. Passing that
    joined string as PaymentOption.network makes the SDK's initialize() raise
    RouteConfigurationError and 500 /pilot/ping + /base/finality-check."""
    monkeypatch.setattr(settings, "x402_default_network", JOINED_PRODUCTION_NETWORKS)
    pilot_app = FastAPI()
    x402_middleware_pilot.register(pilot_app)
    pilot_client = TestClient(pilot_app)

    ping = pilot_client.get("/pilot/ping")
    assert ping.status_code == 402, ping.text[:300]
    ping_decoded = json.loads(base64.b64decode(ping.headers["payment-required"]))
    ping_nets = [a["network"] for a in ping_decoded["accepts"]]
    assert ping_nets, "402 must advertise at least one rail"
    assert all("," not in n and n.count(":") == 1 for n in ping_nets)
    # Joined production string must never appear as a single network id.
    assert JOINED_PRODUCTION_NETWORKS not in ping_nets
    assert "eip155:42161" not in ping_nets

    finality = pilot_client.get("/base/finality-check", params={"tx": VALID_TX})
    assert finality.status_code == 402, finality.text[:300]
    fin_decoded = json.loads(base64.b64decode(finality.headers["payment-required"]))
    fin_nets = [a["network"] for a in fin_decoded["accepts"]]
    assert all(n.startswith("eip155:") and "," not in n for n in fin_nets)
    assert JOINED_PRODUCTION_NETWORKS not in fin_nets


def test_atomic_options_skip_joined_and_unsupported_ids() -> None:
    server = SimpleNamespace(
        has_registered_scheme=lambda net, _scheme: net.startswith("eip155:"),
        get_supported_kind=lambda _v, net, _scheme: object()
        if net == "eip155:8453"
        else None,
    )
    options = x402_middleware_pilot._atomic_payment_options(
        price="$0.01",
        networks=[
            "eip155:8453",
            "eip155:8453,solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
            "eip155:42161",
        ],
        server=server,
    )
    assert [o.network for o in options] == ["eip155:8453"]


def test_atomic_options_fallback_to_supported_family_rail() -> None:
    """If every listed rail is unsupported, advertise a same-family kind the
    facilitator actually has so initialize() does not 500 the route."""
    kind = SimpleNamespace(network="eip155:84532", scheme="exact", x402_version=2)
    server = SimpleNamespace(
        has_registered_scheme=lambda *_a, **_k: True,
        get_supported_kind=lambda *_a, **_k: None,
        _supported_responses={"eip155:84532": {"exact": SimpleNamespace(kinds=[kind])}},
    )
    options = x402_middleware_pilot._atomic_payment_options(
        price="$0.01",
        networks=["eip155:8453", "eip155:42161"],
        server=server,
    )
    assert [o.network for o in options] == ["eip155:84532"]


def test_register_is_a_noop_without_pay_to_address(monkeypatch) -> None:
    monkeypatch.setattr(settings, "x402_pay_to_address", None)
    pilot_app = FastAPI()
    x402_middleware_pilot.register(pilot_app)
    pilot_client = TestClient(pilot_app)
    # No route was ever included, so it's a plain 404 -- not a 402, and not a crash.
    assert pilot_client.get("/pilot/ping").status_code == 404


@pytest.mark.parametrize("agent_id", ["dashboard-agent"])
def test_quota_route_untouched(agent_id: str) -> None:
    """Spot-check a second unrelated route family stays reachable."""
    assert client.get(f"/quota/{agent_id}").status_code == 200


# ---------------------------------------------------------------------------
# Ledger accounting: these routes settle real USDC, so they must appear in the
# revenue ledger / /demand — but ONLY for a settlement that actually succeeded.
# ---------------------------------------------------------------------------

FINALITY = "/base/finality-check"


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Redirect ledger writes into a temp dir. The real ledger/*.jsonl are
    records of real payments and must never be touched by a test."""
    d = tmp_path / "ledger"
    d.mkdir()
    monkeypatch.setattr(ledger_io, "LEDGER", d)
    return d


@pytest.fixture(autouse=True)
def _clean_demand(monkeypatch):
    from app import redis_client

    monkeypatch.setattr(demand, "_memory", demand.Counter())
    monkeypatch.setattr(demand, "_memory_last", {})
    monkeypatch.setattr(demand, "_memory_clients", {})
    monkeypatch.setattr(demand, "_memory_ua", {})
    monkeypatch.setattr(redis_client, "client", None)


def _settle_ctx(
    *,
    path: str = FINALITY,
    success: bool = True,
    settled_amount: str | None = None,
    required_amount: str = "10000",
    network: str = "eip155:8453",
    payer: str = "0xBUYER",
    tx: str = "0xdeadbeef",
):
    """A stand-in for the SDK's SettleResultContext (x402/schemas/hooks.py:291)."""
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
            asset="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # Base USDC
        ),
        transport_context=SimpleNamespace(request=SimpleNamespace(path=path)),
    )


def _revenue_rows(ledger_dir) -> list[dict]:
    return list(ledger_io.read_ledger_rows("revenue", limit=None))


def test_a_settled_payment_writes_a_revenue_row(ledger) -> None:
    x402_middleware_pilot._record_settled_revenue(_settle_ctx())

    rows = _revenue_rows(ledger)
    assert len(rows) == 1
    row = rows[0]
    assert row["product_id"] == "base-finality-check"
    assert row["amount_usdc"] == 0.01  # 10000 atomic USDC, not the "$0.01" string
    assert row["network"] == "eip155:8453"
    assert row["tx"] == "0xdeadbeef"
    assert row["payer"] == "0xbuyer"
    assert row["settled"] is True


def test_a_failed_settlement_writes_nothing(ledger) -> None:
    """The whole point of hanging off on_after_settle rather than the payment
    payload: a payment that did not settle must never show as revenue."""
    x402_middleware_pilot._record_settled_revenue(_settle_ctx(success=False))

    assert _revenue_rows(ledger) == []


@pytest.mark.parametrize("bad_success", [None, "true", 1, 0, False])
def test_only_a_literal_success_true_counts(ledger, bad_success) -> None:
    """`success` is checked with `is True`, not truthiness — a facilitator
    response that merely parses is not proof that funds moved."""
    ctx = _settle_ctx()
    ctx.result.success = bad_success

    x402_middleware_pilot._record_settled_revenue(ctx)

    assert _revenue_rows(ledger) == []


def test_a_settlement_for_an_unrelated_path_is_not_recorded(ledger) -> None:
    x402_middleware_pilot._record_settled_revenue(_settle_ctx(path="/some/other/route"))

    assert _revenue_rows(ledger) == []


def test_the_settled_amount_beats_the_required_amount(ledger) -> None:
    """A partial settlement earns what the facilitator says it earned."""
    x402_middleware_pilot._record_settled_revenue(
        _settle_ctx(settled_amount="4000", required_amount="10000")
    )

    assert _revenue_rows(ledger)[0]["amount_usdc"] == 0.004


def test_the_listed_price_is_the_last_resort(ledger) -> None:
    """Neither the settlement nor the requirements carried a usable amount."""
    ctx = _settle_ctx(settled_amount=None, required_amount="not-a-number")

    x402_middleware_pilot._record_settled_revenue(ctx)

    assert _revenue_rows(ledger)[0]["amount_usdc"] == 0.01  # settings.finality_check_price


def test_the_hook_never_raises_into_the_request_path(ledger, monkeypatch) -> None:
    """The SDK does not wrap resource-server after-settle hooks: an exception
    here escapes process_settlement and the middleware turns a settled payment
    into a 402. A ledger row is never worth a lost sale."""

    def boom(**_kwargs):
        raise RuntimeError("redis is on fire")

    monkeypatch.setattr(ledger_writer, "record_revenue", boom)

    x402_middleware_pilot._record_settled_revenue(_settle_ctx())  # must not raise

    # And a context that is nothing like the SDK's is survivable too.
    x402_middleware_pilot._record_settled_revenue(object())
    x402_middleware_pilot._record_settled_revenue(None)


def test_register_wires_the_after_settle_hook(monkeypatch) -> None:
    """Pins the actual wiring — the hook is useless if nobody registers it."""
    from app import x402_services

    hooks = []
    fake_server = SimpleNamespace(
        on_after_settle=hooks.append,
        has_registered_scheme=lambda *_a, **_k: True,
        get_supported_kind=lambda *_a, **_k: object(),
    )
    monkeypatch.setattr(x402_services, "_resource_server", lambda *a, **k: fake_server)

    added = []
    pilot_app = FastAPI()
    monkeypatch.setattr(
        pilot_app, "add_middleware", lambda cls, **kw: added.append((cls, kw))
    )
    x402_middleware_pilot.register(pilot_app)

    assert hooks == [x402_middleware_pilot._record_settled_revenue]
    assert added and added[0][1]["server"] is fake_server
    # And the middleware installed is the instrumented subclass, so challenges
    # get counted as well as revenue.
    from x402.http.middleware import PaymentMiddlewareASGI

    assert issubclass(added[0][0], PaymentMiddlewareASGI)


# --- top of the funnel -----------------------------------------------------


def test_a_402_records_a_challenge_under_the_revenue_product_id() -> None:
    """demand joins to revenue on this exact string (app/demand.py:246-255);
    if the two ever drift, /demand reports the product as never having sold."""
    client.get(FINALITY, params={"tx": VALID_TX})

    assert demand.challenges().get("base-finality-check") == 1
    assert x402_middleware_pilot.PRODUCT_IDS[FINALITY] == "base-finality-check"


def test_the_ping_pilot_is_counted_too() -> None:
    client.get("/pilot/ping")

    assert demand.challenges().get("pilot-ping") == 1


def test_self_traffic_is_not_counted_as_demand() -> None:
    """Same header the hand-rolled products honour (app/main.py:685), so the
    uptime monitor cannot inflate the funnel forever."""
    client.get(FINALITY, params={"tx": VALID_TX}, headers={"x-demand-ignore": "1"})

    assert demand.challenges() == {}


def test_a_402_after_a_signature_is_a_failed_payment_not_a_view() -> None:
    """A settlement failure returns 402 too. Counting it as a fresh look would
    depress the conversion of the product that is actually converting."""
    client.get(
        FINALITY, params={"tx": VALID_TX}, headers={"PAYMENT-SIGNATURE": "garbage"}
    )

    assert demand.challenges() == {}


def test_unrelated_402s_are_not_attributed_to_these_routes() -> None:
    """The middleware sees every request; only its own two routes count."""
    client.get("/mn/property-check", params={"address": "1 Test St"})

    assert "base-finality-check" not in demand.challenges()
    assert "pilot-ping" not in demand.challenges()


def test_the_funnel_joins_end_to_end(ledger) -> None:
    """A view and a sale for the same product must land on one /demand row."""
    client.get(FINALITY, params={"tx": VALID_TX})
    x402_middleware_pilot._record_settled_revenue(_settle_ctx())

    report = demand.build_report()
    row = next(r for r in report["resources"] if r["resource"] == "base-finality-check")
    assert row["challenges_served"] == 1
    assert row["sales_settled"] == 1
    assert row["revenue_usdc"] == 0.01
