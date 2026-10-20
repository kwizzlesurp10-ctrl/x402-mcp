"""CDP / Coinbase JWT helpers — dynamic URI components, 120s expiry, safe debug.

Follows Coinbase JWT auth guidance:
- Build URI at runtime from method + host + path (never hard-code one endpoint)
- Default exp = 120 seconds
- Header: alg (EdDSA|ES256) + kid + nonce; lean payload only
- Never log full secrets

Refs: https://docs.cdp.coinbase.com/get-started/authentication/jwt-authentication
"""

from __future__ import annotations

import base64
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.serialization import load_pem_private_key


# Common CDP / Coinbase hosts (pick the one that matches the product + key)
HOST_CDP_PLATFORM = "api.cdp.coinbase.com"
HOST_CDP_SANDBOX = "sandbox.cdp.coinbase.com"
HOST_COINBASE_APP = "api.coinbase.com"
HOST_DEVELOPER = "api.developer.coinbase.com"

DEFAULT_EXPIRES_IN = 120


@dataclass(frozen=True)
class RequestTarget:
    """Runtime URI components for one API call."""

    method: str
    host: str
    path: str

    def __post_init__(self) -> None:
        method = self.method.upper().strip()
        host = self.host.strip().removeprefix("https://").removeprefix("http://").split("/")[0]
        path = self.path if self.path.startswith("/") else f"/{self.path}"
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "path", path)

    @property
    def uri_claim(self) -> str:
        """Coinbase JWT uri claim: '{METHOD} {host}{path}'."""
        return f"{self.method} {self.host}{self.path}"

    @property
    def url(self) -> str:
        return f"https://{self.host}{self.path}"

    @classmethod
    def from_url(cls, method: str, url: str) -> RequestTarget:
        """Split a full URL into host + path for JWT binding."""
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = parsed.netloc or parsed.path.split("/")[0]
        path = parsed.path if parsed.netloc else "/" + "/".join(parsed.path.split("/")[1:])
        if parsed.query:
            path = f"{path}?{parsed.query}"
        if not path.startswith("/"):
            path = f"/{path}"
        return cls(method=method, host=host, path=path or "/")


def parse_private_key(
    key_secret: str,
) -> tuple[ec.EllipticCurvePrivateKey | ed25519.Ed25519PrivateKey, str]:
    """Parse PEM EC or base64 Ed25519 secret. Returns (key, alg)."""
    secret = key_secret.strip().strip('"').strip("'")
    # Preserve PEM newlines if stored as literal \n in .env
    if "\\n" in secret and "BEGIN" in secret:
        secret = secret.replace("\\n", "\n")

    if "BEGIN" in secret:
        key = load_pem_private_key(secret.encode(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError("PEM key must be EC (ES256) for Coinbase ECDSA keys")
        return key, "ES256"

    # Ed25519: base64 of 64 bytes (seed || public)
    raw = base64.b64decode(secret)
    if len(raw) != 64:
        raise ValueError(f"Ed25519 secret must decode to 64 bytes, got {len(raw)}")
    seed = raw[:32]
    key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
    return key, "EdDSA"


def key_debug_info(api_key_id: str, api_key_secret: str) -> dict[str, Any]:
    """Safe runtime debug for key import issues (no secret material)."""
    secret = api_key_secret.strip().strip('"').strip("'")
    info: dict[str, Any] = {
        "key_id_len": len(api_key_id or ""),
        "key_id_prefix": (api_key_id or "")[:8] + "..." if api_key_id else "",
        "secret_len": len(secret),
        "secret_looks_pem": "BEGIN" in secret,
        "secret_has_literal_backslash_n": "\\n" in secret and "BEGIN" in secret,
        "secret_padding": len(secret) - len(secret.rstrip("=")),
    }
    try:
        _, alg = parse_private_key(secret)
        info["alg"] = alg
        info["parse_ok"] = True
        if alg == "EdDSA":
            info["decoded_bytes"] = 64
    except Exception as exc:  # noqa: BLE001 — diagnostic only
        info["parse_ok"] = False
        info["parse_error"] = f"{type(exc).__name__}: {exc}"
    return info


def generate_cdp_jwt(
    *,
    api_key_id: str,
    api_key_secret: str,
    target: RequestTarget,
    expires_in: int = DEFAULT_EXPIRES_IN,
    audience: list[str] | None = None,
    use_uris_array: bool = True,
) -> str:
    """Generate a CDP Bearer JWT bound to one request target.

    Args:
        api_key_id: Key name / UUID (kid + sub).
        api_key_secret: PEM EC or base64 Ed25519 private key (original formatting).
        target: Dynamic method/host/path for this call only.
        expires_in: Seconds until exp (default 120; increase slightly behind proxies).
        audience: Optional aud claim (some samples use ['cdp_service']).
        use_uris_array: If True (CDP SDK style), claim is uris=[uri]; else uri=uri (docs samples).
    """
    if not api_key_id:
        raise ValueError("api_key_id (key name) is required")
    if not api_key_secret:
        raise ValueError("api_key_secret (private key) is required")

    private_key, algorithm = parse_private_key(api_key_secret)
    now = int(time.time())

    header = {
        "alg": algorithm,
        "kid": api_key_id,
        "typ": "JWT",
        "nonce": secrets.token_hex(16),
    }

    # Lean payload — only essential claims
    claims: dict[str, Any] = {
        "sub": api_key_id,
        "iss": "cdp",
        "nbf": now,
        "exp": now + max(30, expires_in),
    }
    if audience is not None:
        claims["aud"] = audience

    uri = target.uri_claim
    if use_uris_array:
        claims["uris"] = [uri]
    else:
        claims["uri"] = uri

    return jwt.encode(claims, private_key, algorithm=algorithm, headers=header)


def inspect_jwt_unverified(token: str) -> dict[str, Any]:
    """Decode JWT without verifying signature — for local debugging only."""
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(token, options={"verify_signature": False})
    return {
        "header": {
            "alg": header.get("alg"),
            "kid_prefix": str(header.get("kid", ""))[:8] + "...",
            "typ": header.get("typ"),
            "has_nonce": "nonce" in header,
        },
        "payload": {
            "sub_prefix": str(payload.get("sub", ""))[:8] + "...",
            "iss": payload.get("iss"),
            "aud": payload.get("aud"),
            "nbf": payload.get("nbf"),
            "exp": payload.get("exp"),
            "ttl_s": (payload.get("exp") or 0) - (payload.get("nbf") or 0),
            "uri": payload.get("uri"),
            "uris": payload.get("uris"),
        },
        "clock": {
            "now": int(time.time()),
            "nbf_skew_s": int(time.time()) - int(payload.get("nbf") or 0),
            "seconds_until_exp": int(payload.get("exp") or 0) - int(time.time()),
        },
    }
