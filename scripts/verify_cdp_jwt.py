#!/usr/bin/env python3
"""Verify CDP JWT construction per Coinbase guidance (no secret leakage).

Usage:
  python scripts/verify_cdp_jwt.py
  python scripts/verify_cdp_jwt.py --method POST --host api.cdp.coinbase.com --path /platform/v2/evm/faucet

Checks:
  - Key id + secret import (lengths/alg only)
  - Dynamic METHOD + host + path URI claim
  - 120s default expiry / clock skew
  - Header alg + kid
  - Optional live probe (Authorization Bearer)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.cdp_jwt import (  # noqa: E402
    DEFAULT_EXPIRES_IN,
    HOST_CDP_PLATFORM,
    RequestTarget,
    generate_cdp_jwt,
    inspect_jwt_unverified,
    key_debug_info,
)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def probe(method: str, url: str, token: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        method=method.upper(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read()[:300].decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode("utf-8", errors="replace")
        return e.code, body
    except Exception as e:  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}"


def main() -> int:
    p = argparse.ArgumentParser(description="Verify CDP JWT URI components + auth")
    p.add_argument("--method", default="GET")
    p.add_argument("--host", default=HOST_CDP_PLATFORM)
    p.add_argument("--path", default="/platform/v2/evm/accounts")
    p.add_argument("--expires-in", type=int, default=DEFAULT_EXPIRES_IN)
    p.add_argument("--no-probe", action="store_true")
    p.add_argument("--env", default=str(ROOT / ".env"))
    p.add_argument(
        "--uri-style",
        choices=("uris", "uri", "both"),
        default="both",
        help="Claim shape: CDP SDK uses uris[]; some samples use uri string",
    )
    args = p.parse_args()

    env = load_env(Path(args.env))
    kid = env.get("CDP_API_KEY_ID") or env.get("KEY_NAME") or ""
    sec = env.get("CDP_API_KEY_SECRET") or env.get("KEY_SECRET") or ""

    print("=== 1. Key import (safe debug) ===")
    info = key_debug_info(kid, sec)
    print(json.dumps(info, indent=2))
    if not info.get("parse_ok"):
        print("FAIL: cannot parse private key — check formatting / PEM newlines")
        return 2

    target = RequestTarget(method=args.method, host=args.host, path=args.path)
    print("\n=== 2. URI components (runtime) ===")
    print(
        json.dumps(
            {
                "method": target.method,
                "host": target.host,
                "path": target.path,
                "uri_claim": target.uri_claim,
                "url": target.url,
            },
            indent=2,
        )
    )

    styles = [True, False] if args.uri_style == "both" else [args.uri_style == "uris"]
    exit_code = 0

    for use_uris in styles:
        label = "uris[]" if use_uris else "uri"
        print(f"\n=== 3. JWT ({label}, exp={args.expires_in}s) ===")
        try:
            token = generate_cdp_jwt(
                api_key_id=kid,
                api_key_secret=sec,
                target=target,
                expires_in=args.expires_in,
                audience=["cdp_service"] if not use_uris else None,
                use_uris_array=use_uris,
            )
        except Exception as e:  # noqa: BLE001
            print(f"FAIL generate: {type(e).__name__}: {e}")
            exit_code = 3
            continue

        meta = inspect_jwt_unverified(token)
        print(json.dumps(meta, indent=2))

        # Pitfall checks
        hdr = meta["header"]
        pay = meta["payload"]
        clock = meta["clock"]
        if hdr.get("alg") not in ("EdDSA", "ES256"):
            print(f"WARN: unexpected alg {hdr.get('alg')}")
        if not hdr.get("has_nonce"):
            print("WARN: missing nonce in header")
        if abs(clock.get("nbf_skew_s", 0)) > 30:
            print(
                f"WARN: clock skew nbf_skew_s={clock.get('nbf_skew_s')} — sync NTP"
            )
        if pay.get("ttl_s", 0) > 600:
            print("WARN: TTL very long — Coinbase samples use 120s")

        if args.no_probe:
            continue

        print(f"\n=== 4. Live probe ({label}) ===")
        status, body = probe(target.method, target.url, token)
        print(f"HTTP {status}")
        print(body[:200])
        if status == 200:
            print(f"PASS auth with claim style {label}")
        elif status == 401:
            print(f"FAIL 401 with claim style {label} — key/project mismatch or wrong host")
            exit_code = max(exit_code, 1)
        else:
            print(f"NOTE non-200 ({status}) — may still be valid auth with bad path")

    print("\n=== Pitfall checklist ===")
    print(
        """
[ ] Method/host/path set per-request (dynamic), not a stale JWT
[ ] Host matches product: api.cdp.coinbase.com (CDP) vs api.coinbase.com (App/Trade)
[ ] Path is the exact endpoint (e.g. /platform/v2/evm/accounts)
[ ] expires_in ~ 120s (proxy latency → bump carefully)
[ ] Key name (id) + privateKey imported with original formatting
[ ] Clock in sync (nbf/exp)
[ ] Header alg + kid correct; no payload bloat
"""
    )
    return exit_code


if __name__ == "__main__":
    # Small sleep not needed; nbf uses local clock
    _ = time.time()
    raise SystemExit(main())
