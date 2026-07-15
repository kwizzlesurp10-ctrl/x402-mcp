"""GET /wallet — public data only, no key material."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FORBIDDEN = ("private_key", "evm_private_key", "EVM_PRIVATE_KEY")


def _walk_strings(obj: object, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = str(key).lower()
            if any(f in key_lower for f in ("private_key", "evm_private")):
                found.append(f"{path}.{key}")
            found.extend(_walk_strings(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            found.extend(_walk_strings(item, f"{path}[{i}]"))
    elif isinstance(obj, str):
        for token in FORBIDDEN:
            if token in obj:
                found.append(f"{path}:contains:{token}")
    return found


def test_wallet_response_shape() -> None:
    response = client.get("/wallet")
    assert response.status_code == 200
    body = response.json()
    assert "receive_address" in body
    assert "vault_address" in body
    assert "balances" in body
    assert "sepolia_usdc_atomic" in body["balances"]
    assert "mainnet_usdc_atomic" in body["balances"]
    assert "faucet_url" in body


def test_wallet_never_serializes_private_key() -> None:
    response = client.get("/wallet")
    text = response.text.lower()
    assert "private_key" not in text
    assert "evm_private_key" not in text
    leaks = _walk_strings(json.loads(response.text))
    assert leaks == []