"""Coinbase CDP facilitator authentication.

The CDP x402 facilitator (Base mainnet settlement) requires a per-request
Ed25519 JWT bearer token. The x402 SDK's facilitator client accepts a
`create_headers` callable that returns per-endpoint auth headers; this module
builds that callable.

CDP JWT format (per docs.cdp.coinbase.com JWT authentication):
    header : {alg: "EdDSA", typ: "JWT", kid: <key_id>, nonce: <hex>}
    claims : {sub: <key_id>, iss: "cdp", aud: ["cdp_service"],
              nbf: now, exp: now+120, uri: "<METHOD> <host><path>"}

The api_key_secret is a base64-encoded 64-byte Ed25519 key (32-byte seed +
32-byte public key); we sign with the seed.
"""

from __future__ import annotations

import base64
import secrets
import time
from collections.abc import Callable
from urllib.parse import urlparse

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Endpoint suffixes the x402 facilitator client appends to the base URL, with
# their HTTP methods. The JWT `uri` claim must match the request exactly.
_ENDPOINTS: dict[str, tuple[str, str]] = {
    "verify": ("POST", "/verify"),
    "settle": ("POST", "/settle"),
    "supported": ("GET", "/supported"),
}


def _load_ed25519_key(api_key_secret: str) -> Ed25519PrivateKey:
    raw = base64.b64decode(api_key_secret)
    if len(raw) not in (32, 64):
        raise ValueError(
            f"CDP api_key_secret must decode to 32 or 64 bytes, got {len(raw)}"
        )
    seed = raw[:32]  # 64-byte form is seed || public key; sign with the seed
    return Ed25519PrivateKey.from_private_bytes(seed)


def generate_cdp_jwt(
    api_key_id: str,
    api_key_secret: str,
    method: str,
    host: str,
    path: str,
    expires_in: int = 120,
) -> str:
    """Mint a CDP Ed25519 JWT for a single REST request."""
    key = _load_ed25519_key(api_key_secret)
    now = int(time.time())
    claims = {
        "sub": api_key_id,
        "iss": "cdp",
        "aud": ["cdp_service"],
        "nbf": now,
        "exp": now + expires_in,
        "uri": f"{method} {host}{path}",
    }
    headers = {"kid": api_key_id, "typ": "JWT", "nonce": secrets.token_hex(16)}
    return pyjwt.encode(claims, key, algorithm="EdDSA", headers=headers)


def build_cdp_create_headers(
    api_key_id: str,
    api_key_secret: str,
    base_url: str,
) -> Callable[[], dict[str, dict[str, str]]]:
    """Return a create_headers() callable for HTTPFacilitatorClient.

    Produces a fresh per-endpoint bearer token on each call (tokens expire in
    120s, so they are minted per request batch).
    """
    parsed = urlparse(base_url)
    host = parsed.netloc
    base_path = parsed.path.rstrip("/")

    def create_headers() -> dict[str, dict[str, str]]:
        headers: dict[str, dict[str, str]] = {}
        for name, (method, suffix) in _ENDPOINTS.items():
            token = generate_cdp_jwt(
                api_key_id, api_key_secret, method, host, f"{base_path}{suffix}"
            )
            headers[name] = {"Authorization": f"Bearer {token}"}
        return headers

    return create_headers
