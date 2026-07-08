"""Shared pytest fixtures."""

from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _Handler402(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(402)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def probe_402_url() -> str:
    """Local HTTP server returning 402 — avoids flaky httpbin.org outages."""
    server = HTTPServer(("127.0.0.1", 0), _Handler402)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/paid"
    server.shutdown()