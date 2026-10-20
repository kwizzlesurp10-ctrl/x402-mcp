"""settle_once.py builds a valid payment input before it ever reaches the network.

The first cut of this script passed headers=None for the no-body case, which
PayAndFetchInput rejects — so every GET (the common case) died on a validation
error instead of paying. Cheap to guard, and the failure is invisible until you
actually try to spend.
"""

from __future__ import annotations

import asyncio

import pytest

from app.models import PayAndFetchInput
from scripts import settle_once
from scripts.settle_once import CAP_SOURCE, _extract_tx, parse_args, resolve_amount


def _input_from(args) -> PayAndFetchInput:
    """Mirror how settle_once.main builds its payment input."""
    return PayAndFetchInput(
        url=args.url,
        method=args.method.upper(),
        headers={"Content-Type": args.content_type} if args.body else {},
        body=args.body,
        preferred_network=args.network,
        max_price_usdc=args.max_usdc,
    )


def test_a_get_with_no_body_builds_a_valid_input() -> None:
    args = parse_args(["--url", "https://example.test/r", "--max-usdc", "0.05"])

    payload = _input_from(args)

    assert payload.headers == {}  # not None — pydantic rejects that
    assert payload.method == "GET"
    assert payload.max_price_usdc == 0.05
    assert payload.preferred_network == "eip155:8453"


def test_a_post_with_a_body_sets_the_content_type() -> None:
    args = parse_args(
        [
            "--url", "https://example.test/search",
            "--max-usdc", "0.01",
            "--method", "post",
            "--body", '{"query": "x402"}',
        ]
    )

    payload = _input_from(args)

    assert payload.method == "POST"
    assert payload.headers == {"Content-Type": "application/json"}
    assert payload.body == '{"query": "x402"}'


def test_the_price_cap_is_required() -> None:
    """Never let this script run without a ceiling on what it may spend."""
    with pytest.raises(SystemExit):
        parse_args(["--url", "https://example.test/r"])


def test_tx_is_pulled_from_any_of_the_facilitator_spellings() -> None:
    assert _extract_tx({"transaction": "0xa"}) == "0xa"
    assert _extract_tx({"txHash": "0xb"}) == "0xb"
    assert _extract_tx({"transactionHash": "0xc"}) == "0xc"
    assert _extract_tx({}) is None
    assert _extract_tx(None) is None


# ---------------------------------------------------------------------------
# The ledger records what was CHARGED, not the cap. warden computes its
# daily/monthly caps off this ledger (app/swarm/policy.py:65-83), so recording
# a $0.01 ceiling for a $0.001 resource compounds into refused future buys.
# ---------------------------------------------------------------------------


def test_the_charged_amount_is_recorded_not_the_cap() -> None:
    amount, source = resolve_amount(
        {"amount_charged_usdc": 0.001, "amount_charged_source": "settlement"},
        cap_usdc=0.01,
    )

    assert amount == 0.001  # ten times less than the cap
    assert source == "settlement"


def test_an_authorized_amount_is_used_when_the_facilitator_gave_none() -> None:
    amount, source = resolve_amount(
        {"amount_charged_usdc": 0.005, "amount_charged_source": "authorized"},
        cap_usdc=0.01,
    )

    assert (amount, source) == (0.005, "authorized")


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"amount_charged_usdc": None, "amount_charged_source": None},
        {"amount_charged_usdc": None, "amount_charged_source": "settlement"},
        {"amount_charged_usdc": "not-a-number", "amount_charged_source": "settlement"},
    ],
)
def test_an_unrecoverable_amount_falls_back_to_a_flagged_upper_bound(result) -> None:
    """Falling back to the cap is allowed; pretending it is the real charge
    is not — the row has to say it is only an upper bound."""
    amount, source = resolve_amount(result, cap_usdc=0.01)

    assert amount == 0.01
    assert source == CAP_SOURCE


def _run_main(monkeypatch, pay_result: dict, argv: list[str]) -> list[dict]:
    """Drive settle_once.main with the network and the ledger stubbed out."""
    recorded: list[dict] = []

    async def fake_pay_and_fetch(_params):
        return pay_result

    monkeypatch.setattr(settle_once.x402_services, "pay_and_fetch", fake_pay_and_fetch)
    monkeypatch.setattr(
        settle_once.ledger_writer,
        "record_spend",
        lambda **kw: recorded.append(kw),
    )
    settle_once.main_rc = asyncio.run(settle_once.main(argv))
    return recorded


ARGV = ["--url", "https://example.test/r", "--max-usdc", "0.01"]


def test_a_settled_run_ledgers_the_real_charge(monkeypatch) -> None:
    recorded = _run_main(
        monkeypatch,
        {
            "status_code": 200,
            "payment_settled": True,
            "payment_settlement": {"transaction": "0xabc"},
            "amount_charged_usdc": 0.001,
            "amount_charged_source": "settlement",
        },
        ARGV,
    )

    assert len(recorded) == 1
    assert recorded[0]["amount_usdc"] == 0.001
    assert recorded[0]["amount_source"] == "settlement"
    assert recorded[0]["settled"] is True
    assert settle_once.main_rc == 0


def test_a_settled_run_with_no_recoverable_amount_flags_the_cap(monkeypatch) -> None:
    recorded = _run_main(
        monkeypatch,
        {
            "status_code": 200,
            "payment_settled": True,
            "payment_settlement": {"transaction": "0xabc"},
            "amount_charged_usdc": None,
            "amount_charged_source": None,
        },
        ARGV,
    )

    assert recorded[0]["amount_usdc"] == 0.01
    assert recorded[0]["amount_source"] == CAP_SOURCE


def test_an_unsettled_run_still_records_nothing(monkeypatch) -> None:
    """Unchanged behaviour, re-pinned: no funds moved, no ledger row."""
    recorded = _run_main(
        monkeypatch,
        {
            "status_code": 402,
            "payment_settled": False,
            "payment_settlement": None,
            "amount_charged_usdc": None,
            "amount_charged_source": None,
        },
        ARGV,
    )

    assert recorded == []
    assert settle_once.main_rc == 1


def test_the_cap_still_caps(monkeypatch) -> None:
    """--max-usdc keeps its meaning: it is passed through to pay_and_fetch as
    the hard refusal ceiling, and is not what gets ledgered."""
    seen: dict = {}

    async def fake_pay_and_fetch(params):
        seen["max"] = params.max_price_usdc
        return {
            "status_code": 200,
            "payment_settled": True,
            "payment_settlement": {"transaction": "0xabc"},
            "amount_charged_usdc": 0.002,
            "amount_charged_source": "authorized",
        }

    monkeypatch.setattr(settle_once.x402_services, "pay_and_fetch", fake_pay_and_fetch)
    monkeypatch.setattr(settle_once.ledger_writer, "record_spend", lambda **kw: kw)

    asyncio.run(settle_once.main(ARGV))

    assert seen["max"] == 0.01
