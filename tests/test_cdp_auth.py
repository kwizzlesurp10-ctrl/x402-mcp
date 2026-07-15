"""CDP facilitator JWT auth — verify token structure without hitting the network."""

from __future__ import annotations

import base64

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from app import x402_services
from app.cdp_auth import build_cdp_create_headers, generate_cdp_jwt
from app.config import settings

BASE = "https://api.cdp.coinbase.com/platform/v2/x402"
KEY_ID = "12345678-aaaa-bbbb-cccc-1234567890ab"


def _fake_cdp_secret() -> tuple[str, Ed25519PrivateKey]:
    """Return (base64 64-byte seed||pubkey secret, private key) like a CDP key."""
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    secret_b64 = base64.b64encode(seed + pub).decode()
    return secret_b64, key


def test_generate_jwt_has_correct_claims_and_verifies():
    secret_b64, key = _fake_cdp_secret()
    token = generate_cdp_jwt(
        KEY_ID, secret_b64, "POST", "api.cdp.coinbase.com", "/platform/v2/x402/verify"
    )

    header = pyjwt.get_unverified_header(token)
    assert header["alg"] == "EdDSA"
    assert header["kid"] == KEY_ID
    assert header["typ"] == "JWT"
    assert header["nonce"]

    # Signature must verify against the matching public key.
    claims = pyjwt.decode(
        token, key.public_key(), algorithms=["EdDSA"], audience=["cdp_service"]
    )
    assert claims["sub"] == KEY_ID
    assert claims["iss"] == "cdp"
    assert claims["aud"] == ["cdp_service"]
    assert claims["uri"] == "POST api.cdp.coinbase.com/platform/v2/x402/verify"
    assert claims["exp"] - claims["nbf"] == 120


def test_create_headers_covers_each_endpoint():
    secret_b64, key = _fake_cdp_secret()
    create_headers = build_cdp_create_headers(KEY_ID, secret_b64, BASE)
    headers = create_headers()

    assert set(headers) == {"verify", "settle", "supported"}
    expected_uri = {
        "verify": "POST api.cdp.coinbase.com/platform/v2/x402/verify",
        "settle": "POST api.cdp.coinbase.com/platform/v2/x402/settle",
        "supported": "GET api.cdp.coinbase.com/platform/v2/x402/supported",
    }
    for name, hdr in headers.items():
        token = hdr["Authorization"].removeprefix("Bearer ")
        claims = pyjwt.decode(
            token, key.public_key(), algorithms=["EdDSA"], audience=["cdp_service"]
        )
        assert claims["uri"] == expected_uri[name]


def test_use_cdp_gating(monkeypatch):
    # No creds -> never CDP (default facilitator, unchanged behavior).
    monkeypatch.setattr(settings, "cdp_api_key_id", None)
    monkeypatch.setattr(settings, "cdp_api_key_secret", None)
    assert x402_services._use_cdp("eip155:8453") is False

    # Creds + mainnet in cdp_networks -> CDP; testnet -> default facilitator.
    monkeypatch.setattr(settings, "cdp_api_key_id", KEY_ID)
    monkeypatch.setattr(settings, "cdp_api_key_secret", _fake_cdp_secret()[0])
    monkeypatch.setattr(settings, "cdp_networks", "eip155:8453")
    assert x402_services._use_cdp("eip155:8453") is True
    assert x402_services._use_cdp("eip155:84532") is False
    assert x402_services._facilitator_url_for("eip155:8453") == settings.cdp_facilitator_url
    assert (
        x402_services._facilitator_url_for("eip155:84532")
        == settings.x402_facilitator_url
    )
