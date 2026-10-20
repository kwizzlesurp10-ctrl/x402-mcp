"""market_scan: the Bazaar catalog read as a demand instrument."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "market_scan", ROOT / "scripts" / "market_scan.py"
)
market_scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(market_scan)


def _resource(**over):
    base = {
        "resource": "https://example.com/api",
        "description": "a thing",
        "accepts": [{"amount": "10000"}],  # $0.01
        "quality": {"l30DaysTotalCalls": 100, "l30DaysUniquePayers": 10},
    }
    base.update(over)
    return base


# --- pagination ----------------------------------------------------------------


def test_pagination_terminates_on_total(monkeypatch) -> None:
    pages = {0: [_resource()] * 100, 100: [_resource()] * 50}

    class FakeResponse:
        def __init__(self, items):
            self._items = items

        def raise_for_status(self):
            return None

        def json(self):
            return {"items": self._items, "pagination": {"total": 150}}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params):
            return FakeResponse(pages.get(params["offset"], []))

    monkeypatch.setattr(market_scan.httpx, "Client", lambda **kw: FakeClient())

    assert len(market_scan.fetch_all("https://x")) == 150


def test_pagination_stops_on_a_short_page_without_total(monkeypatch) -> None:
    """The API is the authority on its own envelope; do not loop forever."""

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"items": [_resource()] * 3}  # < PAGE_SIZE, no pagination block

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params):
            return FakeResponse()

    monkeypatch.setattr(market_scan.httpx, "Client", lambda **kw: FakeClient())

    assert len(market_scan.fetch_all("https://x")) == 3


# --- the numbers ---------------------------------------------------------------


def test_price_outlier_flag_fires_at_the_threshold() -> None:
    row = market_scan.summarize(_resource(accepts=[{"amount": "1000000000"}]))

    assert row["price_outlier"] is True
    # A placeholder price must not produce a revenue estimate.
    assert row["est_30d_revenue"] is None


def test_a_normal_price_is_not_flagged() -> None:
    row = market_scan.summarize(_resource())

    assert row["price_outlier"] is False
    assert row["price_usd"] == 0.01
    assert row["est_30d_revenue"] == 1.0


def test_calls_per_payer_is_none_not_a_zero_division() -> None:
    row = market_scan.summarize(
        _resource(quality={"l30DaysTotalCalls": 50, "l30DaysUniquePayers": 0})
    )

    assert row["calls_per_payer"] is None


def test_calls_per_payer_separates_a_wired_in_buyer_from_a_probe_crowd() -> None:
    """The discriminator the whole script exists for."""
    wired = market_scan.summarize(
        _resource(quality={"l30DaysTotalCalls": 23368, "l30DaysUniquePayers": 1})
    )
    probes = market_scan.summarize(
        _resource(quality={"l30DaysTotalCalls": 340, "l30DaysUniquePayers": 340})
    )

    assert wired["calls_per_payer"] == 23368.0
    assert probes["calls_per_payer"] == 1.0


def test_missing_quality_block_does_not_explode() -> None:
    row = market_scan.summarize(_resource(quality={}))

    assert row["calls_30d"] is None
    assert row["calls_per_payer"] is None
    assert row["est_30d_revenue"] is None


def test_missing_accepts_does_not_explode() -> None:
    row = market_scan.summarize(_resource(accepts=[]))

    assert row["price_usd"] is None
    assert row["est_30d_revenue"] is None


# --- filtering -----------------------------------------------------------------


@pytest.mark.parametrize(
    "queries,expected",
    [
        ([], True),
        (["property"], True),  # matches description
        (["minneapolis"], True),  # matches resource
        (["solana"], False),
    ],
)
def test_query_filters_on_both_resource_and_description(queries, expected) -> None:
    row = market_scan.summarize(
        _resource(
            resource="https://x.io/minneapolis/check",
            description="Rental PROPERTY compliance",
        )
    )

    assert market_scan.matches(row, queries) is expected


def test_price_ladder_excludes_outliers() -> None:
    rows = [market_scan.summarize(_resource(accepts=[{"amount": str(a)}])) for a in
            (1000, 4000, 10000, 60000, 162000, 10_000_000_000)]

    ladder = market_scan.price_ladder(rows)

    # Five real prices remain: 0.001 0.004 0.01 0.06 0.162
    assert ladder["median"] == 0.01
    assert ladder["p90"] == 0.162
    # The $10,000 placeholder is excluded rather than dragging the ladder up.
    assert max(ladder.values()) < 1.0
