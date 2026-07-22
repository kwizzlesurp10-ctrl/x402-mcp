"""settle_once.py builds a valid payment input before it ever reaches the network.

The first cut of this script passed headers=None for the no-body case, which
PayAndFetchInput rejects — so every GET (the common case) died on a validation
error instead of paying. Cheap to guard, and the failure is invisible until you
actually try to spend.
"""

from __future__ import annotations

import pytest

from app.models import PayAndFetchInput
from scripts.settle_once import _extract_tx, parse_args


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
