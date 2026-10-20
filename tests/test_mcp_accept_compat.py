"""Smithery-style Accept: application/json must still handshake Streamable HTTP."""

from fastapi.testclient import TestClient

from app.main import app

_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "smithery-compat", "version": "0.0.1"},
    },
}


def test_json_only_accept_initializes_instead_of_406() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/mcp/mcp",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=_INIT,
        )

    assert response.status_code != 406
    assert "Not Acceptable" not in response.text
    assert response.status_code == 200
    assert "x402-micropayments" in response.text
    # json_response=True: body is JSON, not an SSE event stream.
    payload = response.json()
    assert payload["result"]["serverInfo"]["name"] == "x402-micropayments"
