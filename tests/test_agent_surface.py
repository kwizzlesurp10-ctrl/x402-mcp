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

    by_name = {r["name"]: r for r in body["resources"]}
    assert by_name["Base tx decision"]["price"] == settings.tx_decision_price
    assert (
        by_name["Minneapolis rental compliance"]["price"]
        == settings.mn_property_check_price
    )
    assert body["challenge_header"] == "PAYMENT-REQUIRED"
    assert body["mcp"]["streamable_http"].endswith("/mcp/mcp")


def test_llms_txt_is_plain_text_with_live_prices() -> None:
    response = client.get("/llms.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert settings.tx_decision_price in response.text
    assert "PAYMENT-SIGNATURE" in response.text


def test_llms_txt_documents_failure_modes_not_just_the_happy_path() -> None:
    text = client.get("/llms.txt").text

    for signal in ("502", "payment_invalid", "422", "staleness"):
        assert signal in text, f"missing failure-mode coverage: {signal}"


def test_the_advertised_endpoints_exist() -> None:
    """Every URL the manifest advertises must answer — no dead doors."""
    body = client.get("/.well-known/x402").json()

    for r in body["resources"]:
        path = r["url"].replace(settings.public_base_url.rstrip("/"), "")
        response = client.get(path)
        # Paid endpoints answer 402/422/503 unpaid; free ones 200. 404 = rot.
        assert response.status_code != 404, f"{path} advertised but missing"
