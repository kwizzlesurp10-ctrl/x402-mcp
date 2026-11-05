"""AgentMail provider helpers — outbound inbox resolution and inbound Svix webhooks."""

from __future__ import annotations

import email.utils
import json
import logging
from typing import Any, Mapping

from svix.webhooks import Webhook, WebhookVerificationError

from app.config import settings

log = logging.getLogger("x402.mailrail_agentmail")

AGENTMAIL_SEND_API = "https://api.agentmail.to/v0/inboxes/{inbox_id}/messages/send"
MESSAGE_RECEIVED = "message.received"


def resolve_inbox_id() -> str:
    """AgentMail inbox id defaults to the configured from address."""
    explicit = (settings.mailrail_inbox_id or "").strip()
    if explicit:
        return explicit
    return settings.mailrail_from_address.strip()


def verify_agentmail_webhook(body: bytes, headers: Mapping[str, str]) -> dict[str, Any]:
    """Verify Svix signature and return parsed JSON payload."""
    secret = settings.mailrail_agentmail_webhook_secret
    if not secret:
        raise AgentMailWebhookConfigError("MAILRAIL_AGENTMAIL_WEBHOOK_SECRET is not configured")

    wh = Webhook(secret)
    try:
        wh.verify(body, dict(headers))
    except WebhookVerificationError as exc:
        raise AgentMailWebhookVerificationError(str(exc)) from exc

    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentMailWebhookVerificationError("Invalid JSON payload") from exc
    if not isinstance(parsed, dict):
        raise AgentMailWebhookVerificationError("Webhook payload must be a JSON object")
    return parsed


def parse_message_received(payload: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]] | None:
    """Map an AgentMail webhook payload to MailRail inbound fields."""
    event_type = payload.get("event_type")
    if event_type != MESSAGE_RECEIVED:
        return None

    message = payload.get("message")
    if not isinstance(message, dict):
        return None

    raw_from = str(message.get("from") or "unknown@unknown")
    _name, addr = email.utils.parseaddr(raw_from)
    sender = addr or raw_from.strip()

    subject = str(message.get("subject") or "(no subject)")
    body = message.get("text") or message.get("preview") or ""
    if not body and message.get("html"):
        body = "[HTML-only message; retrieve full content from AgentMail if needed]"

    metadata: dict[str, Any] = {
        "source": "agentmail_webhook",
        "agentmail_event_id": payload.get("event_id"),
        "agentmail_event_type": event_type,
        "message_id": message.get("message_id"),
        "thread_id": message.get("thread_id"),
        "inbox_id": message.get("inbox_id"),
    }
    thread = payload.get("thread")
    if isinstance(thread, dict):
        metadata["thread_message_count"] = thread.get("message_count")
    return sender, subject, str(body), metadata


class AgentMailWebhookConfigError(Exception):
    """Webhook secret or other configuration is missing."""


class AgentMailWebhookVerificationError(Exception):
    """Signature or payload verification failed."""
