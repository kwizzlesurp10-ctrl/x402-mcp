"""Unit tests for city sample probe + keepalive target selection."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


probe = _load("probe_city_samples", "scripts/probe_city_samples.py")
keepalive = _load("city_keepalive", "scripts/city_keepalive.py")


def test_evaluate_catalog_ok() -> None:
    body = {
        "network": "us-city-open-data-compliance",
        "price": "$0.01",
        "cities": [
            {
                "code": "mn",
                "sample_url": "https://x/us/mn/property-check/sample",
                "paid_url": "https://x/us/mn/property-check",
            }
        ],
    }
    ev = probe.evaluate_catalog(body)
    assert ev["ok"] is True
    assert ev["codes"] == ["mn"]


def test_evaluate_catalog_missing_urls() -> None:
    ev = probe.evaluate_catalog({"cities": [{"code": "sea"}]})
    assert ev["ok"] is False
    assert "missing_urls" in (ev["error"] or "")


def test_evaluate_sample_requires_next_handoff_flag() -> None:
    ok = probe.evaluate_sample(
        {
            "sample": True,
            "city": "chi",
            "sample_address": "1 N",
            "report": {"compliance_verdict": "x"},
            "next": {"mcp_tool": "check_us_city_property", "paid_url": "https://x"},
        },
        city_code="chi",
    )
    assert ok["ok"] is True
    assert ok["has_next_handoff"] is True

    bare = probe.evaluate_sample(
        {
            "sample": True,
            "city": "chi",
            "report": {"compliance_verdict": "x"},
        },
        city_code="chi",
    )
    assert bare["ok"] is True
    assert bare["has_next_handoff"] is False


def test_evaluate_sample_upstream_error() -> None:
    ev = probe.evaluate_sample(
        {"error": "upstream_open_data_unavailable", "detail": "timeout"},
        city_code="nyc",
    )
    assert ev["ok"] is False


def test_keepalive_skips_reverse_clause() -> None:
    row = {"challenges_served": 900, "sales_external": 0}
    ok, reason = keepalive.should_keepalive(
        row, max_challenges_at_zero_external=600, force=False
    )
    assert ok is False
    assert "reverse_clause" in reason

    ok2, _ = keepalive.should_keepalive(
        row, max_challenges_at_zero_external=600, force=True
    )
    assert ok2 is True


def test_keepalive_allows_external_sales() -> None:
    ok, reason = keepalive.should_keepalive(
        {"challenges_served": 9000, "sales_external": 2},
        max_challenges_at_zero_external=600,
        force=False,
    )
    assert ok is True
    assert "external" in reason


def test_build_targets_city_only_no_demoted() -> None:
    cities = [
        {
            "code": "sea",
            "sample_address": "1531 BELMONT AVE",
            "paid_url": "https://x402-mcp.onrender.com/us/sea/property-check",
        },
        {
            "code": "mn",
            "sample_address": "1700 Penn Ave N",
            "paid_url": "https://x402-mcp.onrender.com/us/mn/property-check",
        },
    ]
    demand = {
        "mn-property-check": {"challenges_served": 100, "sales_external": 0},
        "us-city-sea-property-check": {"challenges_served": 50, "sales_external": 0},
    }
    targets = keepalive.build_targets(
        cities,
        base="https://x402-mcp.onrender.com",
        codes=None,
        demand=demand,
        max_challenges_at_zero_external=600,
        force=False,
    )
    urls = " ".join(t["url"] for t in targets)
    assert "/mn/property-check" in urls
    assert "/us/sea/property-check" in urls
    assert "tx-decision" not in urls
    assert "swarm/products" not in urls
    assert all(t["keepalive"] for t in targets)


def test_demand_for_city_prefers_mn_canonical() -> None:
    index = {
        "us-city-mn-property-check": {"challenges_served": 300, "sales_external": 0},
        "mn-property-check": {"challenges_served": 5000, "sales_external": 0},
    }
    row = keepalive.demand_for_city(index, "mn")
    assert row is not None
    assert row["challenges_served"] == 5000
    ok, reason = keepalive.should_keepalive(
        row, max_challenges_at_zero_external=600, force=False
    )
    assert ok is False
    assert "reverse_clause" in reason


def test_build_targets_skips_hot_zero_external_mn() -> None:
    cities = []
    demand = {
        "mn-property-check": {"challenges_served": 5000, "sales_external": 0},
        "us-city-mn-property-check": {"challenges_served": 100, "sales_external": 0},
    }
    targets = keepalive.build_targets(
        cities,
        base="https://x402-mcp.onrender.com",
        codes=["mn"],
        demand=demand,
        max_challenges_at_zero_external=600,
        force=False,
    )
    assert len(targets) == 1
    assert targets[0]["keepalive"] is False
    assert targets[0]["demand"]["challenges"] == 5000
