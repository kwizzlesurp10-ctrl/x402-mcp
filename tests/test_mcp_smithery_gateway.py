"""Smithery gateway compatibility for the Streamable HTTP MCP endpoint.

Regressions covered:
- POST https://host/mcp went 307 -> /mcp/ -> 404, so a gateway or client
  configured with the conventional /mcp URL could not initialize.
- Requests carrying Smithery's gateway Origin
  (https://x402-mcp--kwizzlesurp10.run.tools) were rejected 403
  "Invalid Origin header" and their CORS preflight 400.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mcp_server import mcp


@pytest.fixture(scope="module")
def client():
    # The Streamable HTTP session manager refuses a second run() in one
    # process; reset the guard so this module composes with other lifespan
    # tests regardless of order.
    mcp.session_manager._has_started = False
    with TestClient(app) as c:
        yield c
    mcp.session_manager._has_started = False

GATEWAY_ORIGIN = "https://x402-mcp--kwizzlesurp10.run.tools"
_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _init(version: str = "2025-06-18") -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": version,
            "capabilities": {},
            "clientInfo": {"name": "smithery-gateway-test", "version": "0"},
        },
    }


@pytest.mark.parametrize("path", ["/mcp", "/mcp/", "/mcp/mcp"])
@pytest.mark.parametrize("version", ["2025-06-18", "2025-03-26"])
def test_initialize_and_tools_list_on_every_mcp_path(path: str, version: str, client) -> None:
    init = client.post(path, headers=_HEADERS, json=_init(version), follow_redirects=False)
    assert init.status_code == 200, (path, init.status_code, init.text[:200])
    assert init.json()["result"]["serverInfo"]["name"] == "x402-micropayments"
    hdrs = {**_HEADERS, "MCP-Protocol-Version": version}
    note = client.post(path, headers=hdrs, json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                       follow_redirects=False)
    assert note.status_code == 202
    tools = client.post(path, headers=hdrs, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                        follow_redirects=False)
    assert tools.status_code == 200
    names = {t["name"] for t in tools.json()["result"]["tools"]}
    assert {"city.list", "city.check"} <= names


def test_gateway_origin_is_accepted(client) -> None:
    r = client.post("/mcp/mcp", headers={**_HEADERS, "Origin": GATEWAY_ORIGIN}, json=_init())
    assert r.status_code == 200, r.text[:200]
    assert "Invalid Origin" not in r.text


def test_gateway_origin_preflight_is_allowed(client) -> None:
    r = client.options(
        "/mcp/mcp",
        headers={
            "Origin": GATEWAY_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,mcp-session-id,mcp-protocol-version",
        },
    )
    assert r.status_code == 200, r.text[:200]
    assert r.headers.get("access-control-allow-origin") == GATEWAY_ORIGIN


def test_unknown_origin_still_rejected(client) -> None:
    r = client.post("/mcp/mcp", headers={**_HEADERS, "Origin": "https://evil.example"}, json=_init())
    assert r.status_code == 403


def test_plain_browser_get_on_bare_mcp_is_not_rewritten(client) -> None:
    r = client.get("/mcp", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code != 200 or "text/event-stream" not in r.headers.get("content-type", "")
