"""The x402scan ownership proof: sign the origin, with the payTo key.

Every test here uses a throwaway key generated in-process. No real key is ever
read, written, or asserted against.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from eth_account import Account

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "sign_ownership_proof", ROOT / "scripts" / "sign_ownership_proof.py"
)
sop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sop)

ORIGIN = "https://x402-mcp.onrender.com"


@pytest.fixture
def throwaway():
    """A key that has never held funds and never will."""
    return Account.create()


# --- the origin string is the message ------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (ORIGIN, ORIGIN),
        (ORIGIN + "/", ORIGIN),  # trailing slash stripped
        ("  " + ORIGIN + "  ", ORIGIN),
        ("https://example.com:8402", "https://example.com:8402"),
    ],
)
def test_normalize_accepts_an_origin(raw, expected) -> None:
    assert sop.normalize_origin(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://x402-mcp.onrender.com/mn/property-check",  # a path, not an origin
        "https://x402-mcp.onrender.com/?a=1",
        "x402-mcp.onrender.com",  # no scheme
        "",
    ],
)
def test_normalize_rejects_what_would_sign_the_wrong_message(raw) -> None:
    """A valid signature over the wrong string is indistinguishable from none."""
    with pytest.raises(sop.OriginError):
        sop.normalize_origin(raw)


@pytest.mark.parametrize(
    "raw",
    ["http://localhost:8402", "http://127.0.0.1:8402", "http://0.0.0.0:8402"],
)
def test_normalize_rejects_loopback(raw) -> None:
    """PUBLIC_BASE_URL is localhost on an operator machine — refuse, don't sign."""
    with pytest.raises(sop.OriginError, match="loopback"):
        sop.normalize_origin(raw)


# --- the signature ---------------------------------------------------------------


def test_signature_recovers_to_the_signing_address(throwaway) -> None:
    signature, recovered = sop.sign_origin(ORIGIN, throwaway.key.hex())

    assert recovered.lower() == throwaway.address.lower()
    assert signature.startswith("0x")


def test_signature_is_eip191_personal_sign(throwaway) -> None:
    """What x402scan's viem recoverMessageAddress verifies.

    Pinned by recovering with an independently constructed EIP-191 message
    rather than by trusting the helper's own round-trip.
    """
    from eth_account.messages import encode_defunct

    signature, _ = sop.sign_origin(ORIGIN, throwaway.key.hex())
    recovered = Account.recover_message(encode_defunct(text=ORIGIN), signature=signature)

    assert recovered.lower() == throwaway.address.lower()


def test_a_different_origin_recovers_to_a_different_result(throwaway) -> None:
    """Why the origin must be exact: the signature is over the message."""
    sig_right, _ = sop.sign_origin(ORIGIN, throwaway.key.hex())
    sig_wrong, _ = sop.sign_origin("https://example.com", throwaway.key.hex())

    assert sig_right != sig_wrong

    from eth_account.messages import encode_defunct

    # The wrong-origin signature does NOT verify against the real origin.
    recovered = Account.recover_message(
        encode_defunct(text=ORIGIN), signature=sig_wrong
    )
    assert recovered.lower() != throwaway.address.lower()


def test_a_key_without_the_0x_prefix_still_works(throwaway) -> None:
    bare = throwaway.key.hex().removeprefix("0x")

    _, recovered = sop.sign_origin(ORIGIN, bare)

    assert recovered.lower() == throwaway.address.lower()


@pytest.mark.parametrize("bad", ["", "0xdeadbeef", "not-a-key", "0x" + "z" * 64])
def test_a_malformed_key_is_rejected_before_signing(bad) -> None:
    with pytest.raises(ValueError, match="64 hex"):
        sop.sign_origin(ORIGIN, bad)


def test_the_error_never_echoes_the_key() -> None:
    """A key must not reach a log, a traceback, or a terminal scrollback."""
    secret = "0x" + "a" * 63  # wrong length, so it is rejected

    with pytest.raises(ValueError) as exc:
        sop.sign_origin(ORIGIN, secret)

    assert secret not in str(exc.value)
    assert "aaaa" not in str(exc.value)
