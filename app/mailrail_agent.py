"""Dedicated MailRail Postmaster agent — the only identity allowed to use MailRail.

Public MCP/Smithery does not expose mailrail.* tools. HTTP send/inbound/ledgers
require OPERATOR_TOKEN plus X-Agent-Id matching this agent (or an allowlisted
operator agent). Operator notifications go to GitHub and/or
settings.contact_email (kwizzlesurp10@gmail.com by default).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException, Request

from app.config import settings

log = logging.getLogger("x402.mailrail_agent")

AGENT_ID = "x402-mailrail-postmaster"
AGENT_NAME = "MailRail Postmaster"
AGENT_HEADER = "X-Agent-Id"


def allowed_agent_ids() -> frozenset[str]:
    raw = getattr(settings, "mailrail_allowed_agent_ids", "") or AGENT_ID
    ids = {part.strip() for part in str(raw).split(",") if part.strip()}
    ids.add(AGENT_ID)
    return frozenset(ids)


def is_mailrail_agent(agent_id: str | None) -> bool:
    return bool(agent_id) and agent_id in allowed_agent_ids()


def operator_notify_email() -> str:
    return (
        settings.mailrail_admin_recipient
        or settings.contact_email
        or "kwizzlesurp10@gmail.com"
    )


def _public_contact_email() -> str:
    return settings.contact_email or "kwizzlesurp10@gmail.com"


def agent_card(*, public: bool = False) -> dict[str, Any]:
    base = settings.public_base_url.rstrip("/")
    notify_email = _public_contact_email() if public else operator_notify_email()
    return {
        "id": AGENT_ID,
        "name": AGENT_NAME,
        "role": "postmaster",
        "sole_responsibility": "mailrail",
        "description": (
            "Operator MailRail agent. Sole owner of send, inbound, inbox, "
            "outbox, and ledger. Not a public Smithery tool."
        ),
        "public": False,
        "auth": {
            "http": [
                "Authorization: Bearer $OPERATOR_TOKEN",
                f"{AGENT_HEADER}: {AGENT_ID}",
            ],
            "fail_closed": True,
        },
        "notify": {
            "email": notify_email,
            "github_repo": getattr(settings, "github_repo", None)
            or "kwizzlesurp10-ctrl/x402-mcp",
        },
        "endpoints": {
            "health": f"{base}/mailrail/health",
            "card": f"{base}/agent/mailrail",
            "inbound": f"{base}/mailrail/inbound",
            "inbox": f"{base}/mailrail/inbox",
            "ledger": f"{base}/mailrail/ledger",
            "stats": f"{base}/mailrail/stats",
        },
    }


def extract_agent_id(request: Request) -> str | None:
    header = request.headers.get(AGENT_HEADER) or request.headers.get("x-agent-id")
    if header and header.strip():
        return header.strip()
    q = request.query_params.get("agent_id")
    if q and q.strip():
        return q.strip()
    return None


def authorize_http(request: Request) -> str:
    """Fail closed: bearer OPERATOR_TOKEN and an allowlisted MailRail agent."""
    token = settings.operator_token
    if not token:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "detail": "MailRail send/inbound/ledgers require OPERATOR_TOKEN",
            },
        )
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {token}":
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})

    agent_id = extract_agent_id(request)
    if not is_mailrail_agent(agent_id):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "detail": "MailRail is only available to operator MailRail agents",
                "required_agent_id": AGENT_ID,
            },
        )
    return agent_id or AGENT_ID


def refuse_if_not_mailrail_agent(agent_id: str | None) -> dict[str, Any] | None:
    """Return a tool-error payload if agent_id is not the postmaster."""
    if is_mailrail_agent(agent_id):
        return None
    return {
        "error": {
            "code": "forbidden",
            "detail": "MailRail is only available to operator MailRail agents",
            "required_agent_id": AGENT_ID,
        },
        "data": None,
        "meta": None,
    }


def _github_issue(subject: str, body: str) -> dict[str, Any] | None:
    token = getattr(settings, "github_token", None)
    if not token:
        return None
    repo = getattr(settings, "github_repo", None) or "kwizzlesurp10-ctrl/x402-mcp"
    url = f"https://api.github.com/repos/{repo}/issues"
    try:
        res = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "title": subject[:240],
                "body": body,
                "labels": ["mailrail"],
            },
            timeout=10.0,
        )
        if res.status_code in (200, 201):
            data = res.json()
            return {"ok": True, "html_url": data.get("html_url"), "number": data.get("number")}
        log.warning("GitHub MailRail notify HTTP %s: %s", res.status_code, res.text[:300])
        return {"ok": False, "status": res.status_code}
    except Exception as exc:  # noqa: BLE001 — notify must not break dispatch
        log.warning("GitHub MailRail notify failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def notify_operator(
    subject: str,
    body: str,
    *,
    event_id: str | None = None,
    already_emailed: bool = False,
) -> dict[str, Any]:
    """Notify the operator via GitHub (if token) and/or Gmail/MailRail email."""
    channels: dict[str, Any] = {}
    gh = _github_issue(subject, body)
    if gh is not None:
        channels["github"] = gh

    if not already_emailed:
        try:
            from app import mailrail

            channels["email"] = mailrail.send_agent_mail(
                to=operator_notify_email(),
                subject=subject,
                body=body,
                event_id=(f"notify-{event_id}" if event_id else None),
                metadata={"agent_id": AGENT_ID, "kind": "operator-notify"},
                notify_operator_after=False,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("MailRail email notify failed: %s", exc)
            channels["email"] = {"ok": False, "error": str(exc)}
    return {"agent_id": AGENT_ID, "channels": channels}
