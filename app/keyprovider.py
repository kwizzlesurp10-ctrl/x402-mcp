"""Pluggable signing-key provider — decouple spend authority from env storage.

Storing a raw private key in an environment variable / .env is the flagged
security weakness: a single leaked env exposes full spend authority. This seam
lets the buyer key come from env (with a loud deprecation warning), or — via
KEY_PROVIDER — an OS keychain or a hardware / agentic-wallet handoff, without
changing any caller. Sellers need no key at all (see docs/SELLER-STOREFRONT.md).
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from app.config import settings

logger = logging.getLogger("x402.keyprovider")


@runtime_checkable
class KeyProvider(Protocol):
    name: str

    def get_private_key(self) -> str | None: ...

    def describe(self) -> dict: ...


class EnvKeyProvider:
    """Reads EVM_PRIVATE_KEY from the environment. Deprecated for production."""

    name = "env"
    _warned = False

    def get_private_key(self) -> str | None:
        key = settings.evm_private_key
        if key and not EnvKeyProvider._warned:
            logger.warning(
                "SECURITY: EVM_PRIVATE_KEY is loaded from an environment variable / "
                ".env file. A leaked env exposes full spend authority. This is "
                "deprecated for production — migrate to an OS keychain or a hardware / "
                "agentic-wallet handoff (set KEY_PROVIDER), or run seller-only with no "
                "spend key (docs/SELLER-STOREFRONT.md)."
            )
            EnvKeyProvider._warned = True
        return key

    def describe(self) -> dict:
        return {
            "provider": "env",
            "secure": False,
            "configured": bool(settings.evm_private_key),
            "warning": "raw key in env/.env — deprecated for production",
        }


class MissingKeyProvider:
    """Selected when an unknown/unsupported KEY_PROVIDER is set: never signs."""

    def __init__(self, requested: str) -> None:
        self.name = requested

    def get_private_key(self) -> str | None:
        logger.error(
            "KEY_PROVIDER=%s is not available in this build; buyer signing is "
            "disabled. Supported: %s.",
            self.name,
            ", ".join(sorted(_PROVIDERS)),
        )
        return None

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "secure": None,
            "configured": False,
            "warning": f"provider '{self.name}' not available in this build",
        }


# Registry — keychain / hardware / agentic-wallet providers plug in here.
_PROVIDERS: dict[str, type] = {"env": EnvKeyProvider}


def get_key_provider() -> KeyProvider:
    name = (settings.key_provider or "env").lower()
    cls = _PROVIDERS.get(name)
    if cls is None:
        return MissingKeyProvider(name)
    return cls()


def security_posture() -> dict:
    """Inspectable security posture — surfaced at GET /security."""
    provider = get_key_provider()
    desc = provider.describe()
    recs: list[str] = []
    if desc.get("secure") is False and desc.get("configured"):
        recs.append(
            "Spend key is in env/.env — rotate it, keep .env gitignored, and move to "
            "a keychain/hardware provider (KEY_PROVIDER) for production."
        )
    if not settings.x402_pay_to_address:
        recs.append("Set X402_PAY_TO_ADDRESS to receive sale revenue.")
    return {
        "key_provider": desc,
        "seller_only_possible": bool(settings.x402_pay_to_address),
        "spend_caps_usdc": {
            "note": "enforced by the warden via ledger/policy.json",
        },
        "recommendations": recs,
    }
