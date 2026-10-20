"""Obtain a Vercel Connect token for an external MCP connector.

Two resolution paths, tried in order:

1. ``VERCEL_OIDC_TOKEN`` env var (runtime / ``vc env pull``): exchanged via
   ``POST https://api.vercel.com/v1/connect/token/<connector>``.
2. Vercel CLI fallback (local dev): ``vercel connect token <connector>``,
   which uses the developer's CLI login and may open a browser for
   re-authorization.

The token is returned to the caller, never printed. ``--verify`` proves the
token against the connector's MCP endpoint with a JSON-RPC ``tools/list``.

Usage:
    .venv/Scripts/python scripts/vercel_connect_token.py --verify
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse

import httpx

DEFAULT_CONNECTOR = "huggingface.co/x402-mcp"
DEFAULT_MCP_URL = "https://huggingface.co/mcp"
VERCEL_CONNECT_API = "https://api.vercel.com/v1/connect/token"


def _token_via_oidc(connector: str, oidc_token: str) -> str:
    resp = httpx.post(
        f"{VERCEL_CONNECT_API}/{urllib.parse.quote(connector, safe='')}",
        headers={"Authorization": f"Bearer {oidc_token}"},
        json={"subject": {"type": "user"}},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def _token_via_cli(connector: str) -> str:
    vercel = shutil.which("vercel")
    if not vercel:
        raise RuntimeError("vercel CLI not found and VERCEL_OIDC_TOKEN not set")
    out = subprocess.run(
        [vercel, "connect", "token", connector, "--yes"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip().splitlines()[-1]


def get_connect_token(connector: str = DEFAULT_CONNECTOR) -> str:
    oidc = os.environ.get("VERCEL_OIDC_TOKEN")
    if oidc:
        return _token_via_oidc(connector, oidc)
    return _token_via_cli(connector)


def verify_mcp(token: str, mcp_url: str = DEFAULT_MCP_URL) -> int:
    """Call tools/list on the MCP endpoint; return the tool count."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    with httpx.Client(headers=headers, timeout=30) as client:
        init = client.post(
            mcp_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "x402-mcp", "version": "0.1"},
                },
            },
        )
        init.raise_for_status()
        session_id = init.headers.get("mcp-session-id")
        if session_id:
            client.headers["mcp-session-id"] = session_id
        client.post(
            mcp_url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        listed = client.post(
            mcp_url,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        listed.raise_for_status()
        body = listed.text
        # Streamable HTTP may answer as SSE; extract the data line if so.
        if body.lstrip().startswith("event:") or "\ndata:" in f"\n{body}":
            body = next(
                line[len("data:"):].strip()
                for line in body.splitlines()
                if line.startswith("data:")
            )
        tools = json.loads(body)["result"]["tools"]
        return len(tools)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connector", default=DEFAULT_CONNECTOR)
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="call tools/list on the MCP endpoint with the token",
    )
    args = parser.parse_args()

    token = get_connect_token(args.connector)
    print(f"token acquired for {args.connector} (length {len(token)})")
    if args.verify:
        count = verify_mcp(token, args.mcp_url)
        print(f"MCP endpoint {args.mcp_url} verified: {count} tools listed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
