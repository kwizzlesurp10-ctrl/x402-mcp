"""/llms.txt and /.well-known/x402 — generated from config so they cannot rot.

Every hand-written doc in this repo drifted (10 tools vs 16, $8.00 vs $0.05).
These are built from settings at request time, and the tests pin the property
that matters: the advertised prices ARE the config prices.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_well_known_x402_serves_the_live_prices() -> None:
    body = client.get("/.well-known/x402").json()

    by_name = {r["name"]: r for r in body["resource_details"]}
    assert by_name["Base tx decision"]["price"] == settings.tx_decision_price
    assert (
        by_name["Minneapolis rental compliance"]["price"]
        == settings.mn_property_check_price
    )
    assert body["challenge_header"] == "PAYMENT-REQUIRED"
    assert body["mcp"]["streamable_http"].endswith("/mcp/mcp")


def test_well_known_x402_matches_the_published_fan_out_schema() -> None:
    """x402scan's compat parser wants `version` and bare URL strings; ours
    served `x402_version` and objects, so the fallback document was
    unreadable to the one crawler it exists for."""
    body = client.get("/.well-known/x402").json()

    assert body["version"] == 1
    assert body["resources"] and all(
        isinstance(u, str) and u.startswith("http") for u in body["resources"]
    )
    detail_urls = {r["url"] for r in body["resource_details"] if r["price"] != "free"}
    assert set(body["resources"]) == detail_urls


def test_llms_txt_is_plain_text_with_live_prices() -> None:
    response = client.get("/llms.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert settings.tx_decision_price in response.text
    assert "PAYMENT-SIGNATURE" in response.text
    # Free MN sample is advertised so agents can verify quality before paying.
    assert "/mn/property-check/sample" in response.text
    # Canonical Visit / Resource URLs for Gold402 / 24K / scanners.
    base = settings.public_base_url.rstrip("/")
    assert f"{base}/us/cities" in response.text
    assert f"{base}/us/sea/property-check" in response.text
    assert f"{base}/us/sea/property-check/sample" in response.text


def test_llms_txt_documents_failure_modes_not_just_the_happy_path() -> None:
    text = client.get("/llms.txt").text

    for signal in ("502", "payment_invalid", "422", "staleness"):
        assert signal in text, f"missing failure-mode coverage: {signal}"


def test_the_advertised_endpoints_exist() -> None:
    """Every URL the manifest advertises must answer — no dead doors."""
    body = client.get("/.well-known/x402").json()

    for r in body["resource_details"]:
        path = r["url"].replace(settings.public_base_url.rstrip("/"), "")
        response = client.get(path)
        # Paid endpoints answer 402/422/503 unpaid; free ones 200. 404 = rot.
        assert response.status_code != 404, f"{path} advertised but missing"


def test_a_bare_probe_of_a_paid_endpoint_gets_the_challenge_not_a_422() -> None:
    """How every crawler and agent meets us: a GET with no parameters at all.

    `/mn/property-check` used to answer 422 here, because FastAPI's validation
    of a required `address` ran before any payment logic. "Expected 402, got
    400/422 from request validation running before the payment challenge" is on
    x402scan's published list of registration failures — and that endpoint has
    never been indexed by any catalog, while its 402-clean siblings both were.
    A paid door that answers anything but 402 is a door nobody can find.
    """
    body = client.get("/.well-known/x402").json()
    paid = [r for r in body["resource_details"] if r["price"] != "free"]
    assert paid, "no paid resources advertised"

    for r in paid:
        path = r["url"].replace(settings.public_base_url.rstrip("/"), "")
        response = client.get(path)  # no query parameters, exactly like a crawler
        if response.status_code == 503:
            continue  # seller not configured on this box; nothing to sell
        assert response.status_code == 402, (
            f"{path} answered {response.status_code} to an unparameterised probe; "
            "a discovery crawler will mark it non-registerable"
        )
        assert "payment-required" in {k.lower() for k in response.headers}, (
            f"{path} returned 402 with no PAYMENT-REQUIRED header — an agent "
            "cannot pay a challenge it was never given"
        )
