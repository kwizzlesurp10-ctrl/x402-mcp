"""Produce the x402scan ownership proof for this origin.

x402scan upgrades a listing from "anyone can submit a URL" to ownership-verified
by checking a signature published in your own discovery document - there is no
form to submit and no wallet to connect on their site. From their verifier
(Merit-Systems/x402scan, apps/scan/src/lib/ownership-proof.ts):

    recoverMessageAddress({ message: origin, signature })

So the signed message is the **origin string** ("https://api.example.com" - with
scheme, no trailing slash, no path), the signer must be the **payTo** address,
and the scheme is EIP-191 personal_sign. A signature over anything else recovers
to the wrong address and is silently ignored, which looks identical to having no
proof at all - hence the self-check below.

The key is read with getpass: never an argument, never an env var, never logged,
never written to disk. Only the signature is printed. Run it on the machine
where the receive key lives; this is a message signature, so no transaction is
created and no funds can move.

    .venv\\Scripts\\python.exe scripts/sign_ownership_proof.py --origin https://x402-mcp.onrender.com
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}
PRIVATE_KEY_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


class OriginError(ValueError):
    """The origin string is not what x402scan will hash."""


def normalize_origin(raw: str) -> str:
    """scheme://host[:port], no trailing slash, no path.

    x402scan derives the origin from the resource URL and signs exactly that.
    A path or a trailing slash produces a valid signature over the wrong
    message, which fails verification indistinguishably from no proof.
    """
    candidate = (raw or "").strip()
    if not candidate:
        raise OriginError("origin is empty")

    parsed = urlparse(candidate)
    if not parsed.scheme or not parsed.netloc:
        raise OriginError(
            f"origin must include a scheme and host, e.g. https://example.com "
            f"(got {candidate!r})"
        )
    if parsed.path not in ("", "/"):
        raise OriginError(
            f"origin must not include a path - sign the origin only "
            f"(got path {parsed.path!r} in {candidate!r})"
        )
    if parsed.query or parsed.fragment:
        raise OriginError("origin must not include a query string or fragment")

    host = parsed.hostname or ""
    if host.lower() in LOOPBACK_HOSTS:
        raise OriginError(
            f"{candidate} is a loopback origin and can never be verified in a "
            f"public catalog. Pass --origin with the deployed origin."
        )

    return f"{parsed.scheme}://{parsed.netloc}"


def sign_origin(origin: str, private_key: str) -> tuple[str, str]:
    """Return (signature_hex, recovered_address) for an EIP-191 personal_sign."""
    from eth_account import Account
    from eth_account.messages import encode_defunct

    key = (private_key or "").strip()
    if not key.startswith("0x"):
        key = f"0x{key}"
    if not PRIVATE_KEY_RE.match(key):
        # Deliberately does not echo any part of the value.
        raise ValueError("private key must be 0x followed by 64 hex characters")

    message = encode_defunct(text=origin)
    signed = Account.sign_message(message, private_key=key)
    signature = "0x" + signed.signature.hex().removeprefix("0x")
    recovered = Account.recover_message(message, signature=signed.signature)
    return signature, recovered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--origin",
        default=settings.public_base_url,
        help=(
            "origin to sign. Defaults to PUBLIC_BASE_URL, which is localhost on "
            "an operator machine - pass the deployed origin."
        ),
    )
    parser.add_argument(
        "--pay-to",
        default=settings.x402_pay_to_address,
        help="expected signer; the signature must recover to this address",
    )
    args = parser.parse_args()

    try:
        origin = normalize_origin(args.origin)
    except OriginError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    expected = (args.pay_to or "").strip()
    if not expected:
        print(
            "error: no payTo address. Set X402_PAY_TO_ADDRESS or pass --pay-to. "
            "Without it this cannot check you signed with the right wallet.",
            file=sys.stderr,
        )
        return 2

    print(f"origin to sign : {origin}")
    print(f"expected signer: {expected}")
    print("\nPaste the private key for that address. Input is hidden, is not")
    print("stored, and only the resulting signature is printed.\n")

    key = getpass.getpass("payTo private key: ")
    try:
        signature, recovered = sign_origin(origin, key)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        del key

    if recovered.lower() != expected.lower():
        # The failure this whole script exists to catch: a valid signature from
        # the wrong wallet verifies as nothing and looks like no proof at all.
        print(
            f"\nerror: signature recovers to {recovered}, not {expected}.\n"
            f"That is the wrong wallet - publishing it would read as a failed "
            f"proof. Nothing was written.",
            file=sys.stderr,
        )
        return 1

    print(f"\nverified: recovers to {recovered}\n")
    print("Set this in the Render dashboard (not render.yaml), then redeploy:\n")
    print(f"OWNERSHIP_PROOFS={signature}\n")
    print("Then confirm x-discovery.ownershipProofs is a NON-EMPTY array:")
    print("  curl.exe -s -H \"x-demand-ignore: 1\" \\")
    print(f"    {origin}/openapi.json")
    print("An empty array reads as a FAILED proof - omit the var rather than")
    print("setting it blank.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
