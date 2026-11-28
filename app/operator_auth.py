"""Operator authentication for stats/admin surfaces.

One rule, applied everywhere: an operator is a caller that presents
``OPERATOR_TOKEN`` as ``Authorization: Bearer <token>`` (or the
``X-Operator-Token`` header), compared in constant time. When
``OPERATOR_TOKEN`` is unset, nobody is an operator — every gated surface
fails closed with 503 (operator surface disabled) instead of falling open,
and ``check_operator_token_at_startup`` logs a clear error (or refuses to
start when ``REQUIRE_OPERATOR_TOKEN=true``).

Public responses never carry raw agent ids. Agent ids are the only key the
quota/credit store uses, so a leaked id lets anyone spend that agent's quota,
Pro tier, or prepaid credits. ``redact_agent_ids`` swaps them for a stable,
non-reversible label so dashboards can still group rows.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from fastapi import HTTPException, Request

from app.config import settings

AGENT_ID_KEYS = frozenset({"agent_id", "buyer_agent_id"})

logger = logging.getLogger(__name__)

OPERATOR_TOKEN_MIN_LENGTH = 24
OPERATOR_DISABLED_DETAIL: dict[str, Any] = {
    "error": "operator_surface_disabled",
    "detail": "OPERATOR_TOKEN is not configured on this server; operator routes are closed.",
    "operator_token_configured": False,
}


class OperatorTokenMissing(RuntimeError):
    """Raised at startup when REQUIRE_OPERATOR_TOKEN=true and the token is unset."""


def check_operator_token_at_startup() -> bool:
    """Log (or raise) when the operator credential is missing or weak.

    Returns True when a usable token is configured.
    """
    token = settings.operator_token or ""
    if not token:
        msg = (
            "OPERATOR_TOKEN is not set: /quota, /stats agent list, /pulse/publish, "
            "/swarm/run and MailRail will return 503 until it is configured."
        )
        if settings.require_operator_token:
            raise OperatorTokenMissing(msg + " Refusing to start (REQUIRE_OPERATOR_TOKEN=true).")
        logger.error(msg)
        return False
    if len(token) < OPERATOR_TOKEN_MIN_LENGTH:
        logger.warning(
            "OPERATOR_TOKEN is shorter than %d characters; use a long random value.",
            OPERATOR_TOKEN_MIN_LENGTH,
        )
    return True


def _presented_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth[:7].lower() == "bearer ":
        token = auth[7:].strip()
        if token:
            return token
    alt = request.headers.get("X-Operator-Token", "").strip()
    return alt or None


def operator_token_configured() -> bool:
    return bool(settings.operator_token)


def is_operator(request: Request) -> bool:
    """True only when OPERATOR_TOKEN is set and the request presents it."""
    expected = settings.operator_token
    if not expected:
        return False
    presented = _presented_token(request)
    if not presented:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


def require_operator(request: Request) -> None:
    """Raise 401 unless the caller is the operator; 503 when the token is unset."""
    if is_operator(request):
        return
    if not operator_token_configured():
        raise HTTPException(status_code=503, detail=dict(OPERATOR_DISABLED_DETAIL))
    detail: dict[str, Any] = {
        "error": "unauthorized",
        "hint": "operator surface: send Authorization: Bearer <OPERATOR_TOKEN>",
    }
    raise HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def agent_label(agent_id: Any) -> Any:
    """Stable public stand-in for an agent id (not reversible, not usable)."""
    if not isinstance(agent_id, str) or not agent_id:
        return agent_id
    digest = hashlib.sha256(agent_id.encode()).hexdigest()[:12]
    return f"agt_{digest}"


def redact_agent_ids(value: Any) -> Any:
    """Deep-copy ``value`` replacing every agent-id field with ``agent_label``."""
    if isinstance(value, dict):
        return {
            k: (agent_label(v) if k in AGENT_ID_KEYS else redact_agent_ids(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_agent_ids(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_agent_ids(v) for v in value)
    return value
