"""Cache the x402 PAYMENT-REQUIRED header so selling never depends on a live
facilitator call per request.

`build_seller_requirements` does synchronous facilitator I/O
(`server.initialize()` -> `get_supported`) every time it runs. The CDP
facilitator throws transient 502s, so rebuilding the challenge on every unpaid
request means one facilitator blip turns every 402 into a 500 — the storefront
stops being able to sell while the box itself is perfectly healthy. That is the
"storefront can't sell" failure the monitor exists to catch, and it was
unmitigated for the per-request endpoints (tx-decision, mn-property); the Pulse
listing was already safe because its header lives in the registry.

The header is static per (network, price, resource): it encodes the payment
requirements, not a per-request nonce. So build it once, reuse it, persist it to
Redis, and on a build failure serve the last-known-good. A valid challenge a
buyer can still pay — even one at a slightly stale price during a reprice — beats
no sale. The fingerprint busts the cache when the inputs actually change.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

log = logging.getLogger("x402")

# name -> {"fp": <inputs fingerprint>, "header": <base64 challenge>}
_mem: dict[str, dict[str, str]] = {}


def _redis():
    from app import redis_client

    return redis_client.client


def _redis_key(name: str) -> str:
    return f"challenge:{name}"


def _load(name: str) -> dict[str, str] | None:
    """Warm the in-memory copy from Redis (survives a restart)."""
    if name in _mem:
        return _mem[name]
    client = _redis()
    if client is None:
        return None
    try:
        raw = client.get(_redis_key(name))
    except Exception:  # noqa: BLE001 — cache read must never break a request
        return None
    if not raw:
        return None
    try:
        entry = json.loads(raw)
        if isinstance(entry, dict) and entry.get("header"):
            _mem[name] = {"fp": str(entry.get("fp", "")), "header": entry["header"]}
            return _mem[name]
    except (TypeError, json.JSONDecodeError):
        return None
    return None


def _store(name: str, fp: str, header: str) -> None:
    _mem[name] = {"fp": fp, "header": header}
    client = _redis()
    if client is None:
        return
    try:
        client.set(_redis_key(name), json.dumps({"fp": fp, "header": header}))
    except Exception:  # noqa: BLE001 — a cache write must never break a sale
        log.warning("challenge_cache: failed to persist %s", name)


def get_or_build(name: str, fingerprint: str, builder: Callable[[], str]) -> str:
    """Return a cached challenge for `name`, rebuilding only when it must.

    - fingerprint matches the cache -> serve cached (no facilitator call).
    - fingerprint differs / nothing cached -> build, cache, serve.
    - build fails but ANY cached header exists (even a stale fingerprint) ->
      serve it, logging that we degraded. A stale-priced but valid challenge
      keeps the storefront selling through a facilitator outage.
    - build fails and nothing was ever cached -> re-raise; the caller turns
      this into a retryable 503, not a 500.
    """
    fingerprint = str(fingerprint)
    cached = _load(name)
    if cached and cached.get("fp") == fingerprint:
        return cached["header"]

    try:
        header = builder()
    except Exception as exc:  # noqa: BLE001 — degrade to last-known-good if possible
        if cached and cached.get("header"):
            log.warning(
                "challenge_cache: build failed for %s (%s); serving last-known-good",
                name,
                exc,
            )
            return cached["header"]
        raise

    _store(name, fingerprint, header)
    return header
