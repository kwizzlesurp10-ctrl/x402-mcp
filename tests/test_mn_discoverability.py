"""Minneapolis / Minnesota compliance must be findable on every discovery surface.

Bazaar indexes the canonical /mn/property-check resource; the agent card, the
agents registry and A2A must point agents at the same product, and the generic
``us-city-property-check`` A2A skill the card advertises must actually resolve.
"""

from __future__ import annotations

from app import a2a_rpc, agent_surface


def test_agents_json_lists_mn_compliance_on_bazaar_url() -> None:
    body = agent_surface.agents_json()
    mn = next(a for a in body["agents"] if a["id"] == "mn-rental-compliance")
    assert mn["url"].endswith("/mn/property-check")
    assert any(u.endswith("/us/mn/property-check") for u in mn["alternate_urls"])
    assert mn["free_preview_url"].endswith("/mn/property-check/sample")
    assert {"minnesota", "minneapolis", "mn-compliance"} <= set(mn["tags"])
    assert mn["pricing"]["atomic_units"] > 0
    assert mn["a2a"]["skillId"] == "property-check-mn"


def test_agent_card_mn_skill_mentions_canonical_url_and_state() -> None:
    card = agent_surface.agent_card()
    sk = next(s for s in card["skills"] if s["id"] == "property-check-mn")
    assert "minnesota" in sk["tags"]
    assert any("/mn/property-check?address=" in e and "/us/mn/" not in e for e in sk["examples"])


def test_agent_card_city_network_skill_is_a2a_callable() -> None:
    card = agent_surface.agent_card()
    sk = next(s for s in card["skills"] if s["id"] == "us-city-property-check")
    assert sk["x402"]["paid"] is True
    assert any("skillId" in e and "us-city-property-check" in e for e in sk["examples"])


def test_city_network_alias_routes_to_per_city_binding() -> None:
    bindings = a2a_rpc._skill_bindings()
    sid, inp, err = a2a_rpc._resolve_city_network_alias(
        "us-city-property-check", {"city_code": "MN", "address": "1700 Penn Ave N"}, bindings
    )
    assert err is None
    assert sid == "property-check-mn"
    assert inp == {"address": "1700 Penn Ave N"}


def test_city_network_alias_rejects_unknown_city() -> None:
    bindings = a2a_rpc._skill_bindings()
    sid, _inp, err = a2a_rpc._resolve_city_network_alias(
        "us-city-property-check", {"city_code": "zz", "address": "x"}, bindings
    )
    assert err and "mn" in err
    assert sid == "us-city-property-check"


def test_non_alias_skill_passes_through() -> None:
    bindings = a2a_rpc._skill_bindings()
    out = a2a_rpc._resolve_city_network_alias("property-check-mn", {"address": "a"}, bindings)
    assert out == ("property-check-mn", {"address": "a"}, None)


def test_a2a_message_send_with_city_network_skill_returns_payment_required() -> None:
    """Unpaid A2A call on the generic skill → x402 payment-required, not an error."""
    from fastapi.testclient import TestClient

    from app.a2a_rpc import clear_task_store
    from app.agent_surface import A2A_X402_EXTENSION_URI
    from app.main import app

    clear_task_store()
    try:
        resp = TestClient(app).post(
            "/a2a",
            headers={"X-A2A-Extensions": A2A_X402_EXTENSION_URI},
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [
                            {
                                "kind": "data",
                                "data": {"city_code": "mn", "address": "1700 Penn Ave N"},
                            }
                        ],
                        "metadata": {"skillId": "us-city-property-check"},
                    }
                },
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "error" not in body, body
        task = body["result"]
        assert task["status"]["state"] == "input-required"
        meta = task["status"]["message"]["metadata"]
        assert meta["x402.payment.status"] == "payment-required"
        assert meta["x402.payment.required"]["resource"]["url"].endswith("/us/mn/property-check")
    finally:
        clear_task_store()
