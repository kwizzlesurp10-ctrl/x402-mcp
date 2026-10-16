#!/usr/bin/env python3
"""
Preflight validator for x402 endpoints against Coinbase CDP Bazaar.
Zero-spend validation probe verifying 402 challenge formatting and Bazaar discovery extension.
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx

CDP_VALIDATE_URL = "https://api.cdp.coinbase.com/platform/v2/x402/validate"


def validate_endpoint(resource_url: str, method: str = "GET") -> int:
    payload = {
        "resource": resource_url,
        "method": method.upper(),
    }

    print(f"[*] Validating {method.upper()} {resource_url} via CDP Bazaar...")
    try:
        response = httpx.post(
            CDP_VALIDATE_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15.0,
        )
    except Exception as exc:
        print(f"[!] Request failed: {exc}", file=sys.stderr)
        return 1

    if response.status_code != 200:
        print(
            f"[!] CDP API responded with HTTP {response.status_code}: {response.text}",
            file=sys.stderr,
        )
        return 1

    data = response.json()
    is_valid = data.get("valid", False)
    simulation = data.get("simulation", {})
    outcome = simulation.get("outcome", "unknown")
    preflight = data.get("preflight", {})

    print(f"[*] Valid: {is_valid}")
    print(f"[*] Indexing Simulation Outcome: {outcome}")

    if not is_valid:
        print("\n[!] Preflight Failures:")
        for failure in preflight.get("failures", []):
            print(f"  - {failure}")

    advisories = preflight.get("advisories", [])
    if advisories:
        print("\n[*] Advisories:")
        for adv in advisories:
            print(f"  - {adv}")

    bazaar_ext = data.get("bazaarExtension")
    if bazaar_ext:
        print("\n[*] Detected Bazaar Extension Metadata:")
        print(json.dumps(bazaar_ext, indent=2))

    return 0 if (is_valid and outcome == "accepted") else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Preflight validate an x402 endpoint against Coinbase CDP Bazaar."
    )
    parser.add_argument(
        "--url", required=True, help="Full public HTTPS URL of the payable resource"
    )
    parser.add_argument(
        "--method", default="GET", help="HTTP method (default: GET)"
    )
    args = parser.parse_args()

    sys.exit(validate_endpoint(args.url, args.method))
