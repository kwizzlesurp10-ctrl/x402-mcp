#!/usr/bin/env python3
"""Apply Downloads/cdp_api_key.json into .env and check buyer balances. No secret printing."""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
KEY_CANDIDATES = [
    Path.home() / "Downloads" / "cdp_api_key.json",
    Path("/mnt/c/Users/Keith/Downloads/cdp_api_key.json"),
    Path.home() / "Downloads" / "cdp-api-key.json",
]
BUYER = "0x828942Ea72c767AB944C1cE80264F465b6cB6Fd9"
USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
RPC = "https://sepolia.base.org"


def set_var(text: str, key: str, value: str) -> str:
    pat = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    line = f"{key}={value}"
    if pat.search(text):
        return pat.sub(line, text)
    return text.rstrip() + "\n" + line + "\n"


def find_key() -> Path | None:
    for p in KEY_CANDIDATES:
        if p.exists() and p.stat().st_size > 20:
            return p
    # newest matching download
    dl = Path("/mnt/c/Users/Keith/Downloads")
    if dl.exists():
        hits = sorted(dl.glob("*cdp*key*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if hits:
            return hits[0]
    return None


def rpc(method: str, params: list):
    req = urllib.request.Request(
        RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())["result"]


def main() -> int:
    key_path = find_key()
    if not key_path:
        print("NO_KEY_JSON: place cdp_api_key.json in Downloads and re-run")
        return 2
    data = json.loads(key_path.read_text())
    kid = data.get("id") or data.get("name") or data.get("apiKeyId")
    sec = data.get("privateKey") or data.get("apiKeySecret") or data.get("secret")
    if not kid or not sec:
        print(f"BAD_JSON keys={list(data.keys())} from {key_path}")
        return 3
    text = ENV.read_text() if ENV.exists() else ""
    text = set_var(text, "CDP_API_KEY_ID", str(kid).strip())
    text = set_var(text, "CDP_API_KEY_SECRET", str(sec).strip())
    ENV.write_text(text)
    print(f"APPLIED from {key_path}")
    print(f"CDP_API_KEY_ID len={len(str(kid))} prefix={str(kid)[:8]}...")
    print(f"CDP_API_KEY_SECRET len={len(str(sec))}")

    # balances
    padded = BUYER.lower().replace("0x", "").zfill(64)
    data_hex = "0x70a08231" + padded
    usdc_hex = rpc("eth_call", [{"to": USDC, "data": data_hex}, "latest"])
    eth_hex = rpc("eth_getBalance", [BUYER, "latest"])
    usdc = int(usdc_hex, 16) / 1_000_000
    eth = int(eth_hex, 16) / 1e18
    print(f"buyer {BUYER}")
    print(f"USDC {usdc}")
    print(f"ETH {eth}")
    if usdc > 0 and eth > 0:
        print("FUNDED_OK")
        return 0
    print("FUNDED_PENDING — claim faucet for ETH+USDC on Base Sepolia")
    return 1


if __name__ == "__main__":
    sys.exit(main())
