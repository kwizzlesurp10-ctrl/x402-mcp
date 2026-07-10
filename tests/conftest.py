"""Shared pytest fixtures.

Hermetic by default: a local mock x402 facilitator + CDP discovery server is
started for the whole session and wired in via X402_FACILITATOR_URL /
CDP_DISCOVERY_URL (env vars propagate to stdio subprocess tests; the in-process
`settings` singleton is patched directly). Set X402_LIVE_TESTS=1 to run against
the real x402.org facilitator and Coinbase discovery API instead.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LIVE_TESTS = os.environ.get("X402_LIVE_TESTS") == "1"

# Wire-format (camelCase) SupportedResponse the x402 SDK expects from
# GET {facilitator}/supported — mirrors x402.org for Base + Base Sepolia.
_MOCK_SUPPORTED = {
    "kinds": [
        {"x402Version": 2, "scheme": "exact", "network": "eip155:84532"},
        {"x402Version": 2, "scheme": "exact", "network": "eip155:8453"},
    ],
    "extensions": [],
    "signers": {},
}

_MOCK_DISCOVERY = {
    "items": [
        {
            "resource": "https://example-paid-api.test/data",
            "type": "http",
            "x402Version": 2,
            "accepts": [
                {
                    "scheme": "exact",
                    "network": "eip155:84532",
                    "amount": "10000",
                    "asset": "USDC",
                }
            ],
            "metadata": {"description": "Mock paid endpoint for tests"},
        }
    ]
}


class _MockX402Backend(BaseHTTPRequestHandler):
    """Local stand-in for the x402 facilitator and CDP discovery API."""

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0]
        if path == "/facilitator/supported":
            self._send_json(_MOCK_SUPPORTED)
        elif path == "/discovery/resources":
            self._send_json(_MOCK_DISCOVERY)
        else:
            self._send_json({"error": "not found"}, status=404)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="session", autouse=True)
def mock_x402_backend():
    """Session-wide mock facilitator/discovery server (unless X402_LIVE_TESTS=1).

    Sets env vars so stdio-subprocess servers pick up the mock, and patches the
    already-instantiated in-process `settings` singleton for direct-call tests.
    """
    if LIVE_TESTS:
        yield None
        return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockX402Backend)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    facilitator_url = f"http://127.0.0.1:{port}/facilitator"
    discovery_url = f"http://127.0.0.1:{port}/discovery/resources"

    old_env = {
        "X402_FACILITATOR_URL": os.environ.get("X402_FACILITATOR_URL"),
        "CDP_DISCOVERY_URL": os.environ.get("CDP_DISCOVERY_URL"),
    }
    os.environ["X402_FACILITATOR_URL"] = facilitator_url
    os.environ["CDP_DISCOVERY_URL"] = discovery_url

    from app.config import settings

    old_settings = (settings.x402_facilitator_url, settings.cdp_discovery_url)
    settings.x402_facilitator_url = facilitator_url
    settings.cdp_discovery_url = discovery_url

    yield {"facilitator_url": facilitator_url, "discovery_url": discovery_url}

    settings.x402_facilitator_url, settings.cdp_discovery_url = old_settings
    for key, value in old_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    server.shutdown()


class _Handler402(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        self.send_response(402)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def probe_402_url() -> str:
    """Local HTTP server returning 402 — avoids flaky httpbin.org outages."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler402)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/paid"
    server.shutdown()
