#!/usr/bin/env python3
"""Poll CDP Bazaar until our paid resource appears for X402_PAY_TO_ADDRESS.

Usage:
  python scripts/poll_bazaar_listing.py
  python scripts/poll_bazaar_listing.py --timeout 900 --interval 30
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERCHANT = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant"
SEARCH = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/search"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def check_merchant(pay_to: str) -> list[dict]:
    q = urllib.parse.urlencode({"payTo": pay_to, "limit": 50})
    data = get_json(f"{MERCHANT}?{q}")
    return data.get("resources") or []


def check_search(query: str, network: str) -> list[dict]:
    q = urllib.parse.urlencode(
        {"query": query, "network": network, "limit": 20}
    )
    data = get_json(f"{SEARCH}?{q}")
    return data.get("resources") or []


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--timeout", type=int, default=600, help="seconds to wait")
    p.add_argument("--interval", type=int, default=30, help="poll interval")
    p.add_argument("--query", default="x402-seller-demo")
    args = p.parse_args()

    env = load_env()
    pay_to = env.get("X402_PAY_TO_ADDRESS")
    public = env.get("PUBLIC_BASE_URL", "").rstrip("/")
    network = env.get("X402_DEFAULT_NETWORK", "eip155:84532")
    resource = f"{public}/demo/paid" if public else ""

    if not pay_to:
        print("FAIL: X402_PAY_TO_ADDRESS not set")
        return 2

    print(f"payTo={pay_to}")
    print(f"expect resource contains: {resource or '(any)'}")
    print(f"polling up to {args.timeout}s every {args.interval}s...")

    deadline = time.time() + args.timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            resources = check_merchant(pay_to)
            urls = [r.get("resource") for r in resources]
            print(f"[{attempt}] merchant resources={len(resources)} urls={urls[:5]}")
            if resources:
                if not resource or any(resource in (u or "") for u in urls):
                    print("LISTED")
                    print(json.dumps(resources, indent=2)[:2000])
                    return 0
            # also search
            hits = check_search(args.query, network)
            if resource:
                hits = [h for h in hits if resource in (h.get("resource") or "")]
            if hits:
                print("LISTED via search")
                print(json.dumps(hits, indent=2)[:2000])
                return 0
        except Exception as e:
            print(f"[{attempt}] error: {type(e).__name__}: {e}")
        time.sleep(args.interval)

    print("TIMEOUT — not listed yet. Ensure:")
    print("  1) PUBLIC_BASE_URL is publicly reachable")
    print("  2) X402_FACILITATOR_URL is CDP platform/v2/x402")
    print("  3) At least one settle completed through CDP")
    print("  4) CDP catalog cache can lag ~10 minutes")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
