"""Well-formed unpaid probes for validate-then-402 paid routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.city_compliance import registry as city_registry
from app import mn_compliance

VALID_TX = "0x" + "a" * 64

PROBE_HEADERS = {"x-demand-ignore": "1"}


def probe_unpaid_no_input(client: TestClient, path: str, *, method: str = "GET"):
    """Unpaid probe with no query/body — must still receive a 402 challenge."""
    if path == "/mn/property-check":
        return client.get(path, headers=PROBE_HEADERS)
    if path.startswith("/us/") and path.endswith("/property-check"):
        return client.get(path, headers=PROBE_HEADERS)
    if path == "/base/finality-check":
        return client.get(path, headers=PROBE_HEADERS)
    if path == "/base/tx-decision":
        return client.get(path, headers=PROBE_HEADERS)
    if path == "/agent/property-due-diligence":
        return client.get(path, headers=PROBE_HEADERS)
    if path == "/tasks/us-rental-diligence":
        return client.post(path, headers=PROBE_HEADERS, json={})
    if path == "/x402/policy-check" and method == "POST":
        return client.post(path, headers=PROBE_HEADERS, json={})
    if method == "POST":
        return client.post(path, headers=PROBE_HEADERS)
    return client.get(path, headers=PROBE_HEADERS)


def probe_paid_route(client: TestClient, path: str, *, method: str = "GET"):
    headers = PROBE_HEADERS
    if path == "/mn/property-check":
        return client.get(
            path, params={"address": mn_compliance.SAMPLE_ADDRESS}, headers=headers
        )
    if path.startswith("/us/") and path.endswith("/property-check"):
        code = path.split("/")[2]
        mod = city_registry.get_city(code)
        return client.get(
            path, params={"address": mod.SPEC.sample_address}, headers=headers
        )
    if path == "/base/finality-check":
        return client.get(path, params={"tx": VALID_TX}, headers=headers)
    if path == "/base/tx-decision":
        return client.get(path, headers=headers)
    if path == "/agent/property-due-diligence":
        mod = city_registry.get_city("mn")
        return client.get(
            path,
            params={"city_code": "mn", "address": mod.SPEC.sample_address},
            headers=headers,
        )
    if path == "/tasks/us-rental-diligence":
        mod = city_registry.get_city("mn")
        body = {
            "properties": [{"city_code": "mn", "address": mod.SPEC.sample_address}]
        }
        return client.post(path, json=body, headers=headers)
    if method == "POST":
        return client.post(path, headers=headers, json={})
    return client.get(path, headers=headers)
