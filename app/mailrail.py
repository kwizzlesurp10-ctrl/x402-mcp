"""MailRail — Agent communication, transactional notification, and dispatch rail.

Provides a unified interface for agents (scout, warden, treasurer, merchant, sovereign, profit-oracle)
and background watchers to send alerts, customer receipts, and inter-agent messages.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping

from app.config import settings

log = logging.getLogger("x402.mailrail")

MAILRAIL_LEDGER_FILE = Path("ledger/mailrail.jsonl")
MAILRAIL_INBOX_FILE = Path("ledger/mailrail_inbox.jsonl")
_SEEN_KEYS: set[str] = set()
_AGENTMAIL_TOLERANCE_SECONDS = 5 * 60
_AGENTMAIL_MAX_BODY_BYTES = 1_000_000
_MENTION_RE = re.compile(r"(?<![\w.-])@([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)")


def defuse_mentions(text: str) -> str:
    """Neutralize `@handle` so quoting handles does not trigger unwanted notifications."""
    return _MENTION_RE.sub(lambda m: f"`@{m.group(1)}`", text or "")


def event_key(*parts: object) -> str:
    """Compute stable short id for an event to enforce dedup."""
    joined = "\x1f".join(str(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]


def _record_mail_ledger(record: dict[str, Any]) -> None:
    """Append mail record to ledger/mailrail.jsonl safely."""
    try:
        MAILRAIL_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with MAILRAIL_LEDGER_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        log.warning("Failed to write to mailrail ledger: %s", e)


def _record_inbound_ledger(record: dict[str, Any]) -> None:
    """Append inbound mail record to ledger/mailrail_inbox.jsonl safely."""
    try:
        MAILRAIL_INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
        with MAILRAIL_INBOX_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        log.warning("Failed to write to mailrail inbox ledger: %s", e)


def _dispatch_resend(to: str, subject: str, body: str) -> bool:
    """Dispatch via Resend API."""
    api_key = settings.mailrail_api_key
    if not api_key:
        log.warning("Resend requested but MAILRAIL_API_KEY is not set.")
        return False
    try:
        import httpx
        res = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": settings.mailrail_from_address,
                "to": [to],
                "subject": subject,
                "text": body,
            },
            timeout=10.0,
        )
        return res.status_code in (200, 201)
    except Exception as e:
        log.warning("Resend dispatch failed: %s", e)
        return False


def _dispatch_webhook(to: str, subject: str, body: str) -> bool:
    """Dispatch alert via Discord/Slack webhook."""
    webhook_url = settings.mailrail_webhook_url
    if not webhook_url:
        log.warning("Webhook requested but MAILRAIL_WEBHOOK_URL is not set.")
        return False
    try:
        import httpx
        payload = {
            "content": f"**[MailRail -> {to}] {subject}**\n\n{body}"
        }
        res = httpx.post(webhook_url, json=payload, timeout=10.0)
        return res.status_code in (200, 204)
    except Exception as e:
        log.warning("Webhook dispatch failed: %s", e)
        return False


def send_agent_mail(
    to: str | None,
    subject: str,
    body: str,
    event_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    notify_operator_after: bool = False,
) -> dict[str, Any]:
    """Send an email / notification via MailRail.

    Returns dict containing status ('sent', 'deduplicated', 'disabled', or 'failed'),
    message_id, and delivery timestamp.
    """
    from app.mailrail_agent import AGENT_ID, operator_notify_email

    recipient = to or operator_notify_email()
    meta = dict(metadata or {})
    meta.setdefault("agent_id", AGENT_ID)
    key = event_id or event_key(recipient, subject, body[:100])

    if key in _SEEN_KEYS:
        log.info("MailRail dedup hit for key %s; suppressing.", key)
        return {
            "status": "deduplicated",
            "event_id": key,
            "to": recipient,
            "subject": subject,
            "delivered": False,
        }

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    clean_body = defuse_mentions(body)
    clean_subject = defuse_mentions(subject)

    provider = (settings.mailrail_provider or "mock").lower()
    live_success = True

    if settings.mailrail_enabled:
        if provider == "resend":
            live_success = _dispatch_resend(recipient, clean_subject, clean_body)
        elif provider == "webhook":
            live_success = _dispatch_webhook(recipient, clean_subject, clean_body)

    record = {
        "ts": now_iso,
        "event_id": key,
        "to": recipient,
        "from": settings.mailrail_from_address,
        "subject": clean_subject,
        "body": clean_body,
        "provider": provider,
        "metadata": meta,
        "status": "sent" if live_success else "dispatch_failed",
    }

    _record_mail_ledger(record)
    _SEEN_KEYS.add(key)

    log.info("MailRail dispatched mail to %s via %s (event_id=%s)", recipient, provider, key)
    result = {
        "status": "sent" if live_success else "dispatch_failed",
        "event_id": key,
        "to": recipient,
        "subject": clean_subject,
        "delivered": live_success,
        "timestamp": now_iso,
        "agent_id": meta.get("agent_id"),
    }
    # Default off. notify_operator passes False so email notify cannot recurse.
    if notify_operator_after and live_success:
        try:
            from app.mailrail_agent import notify_operator

            already = recipient.lower() == operator_notify_email().lower()
            result["operator_notify"] = notify_operator(
                clean_subject,
                clean_body,
                event_id=key,
                already_emailed=already,
            )
        except Exception as exc:  # noqa: BLE001 — notify must not fail the send
            log.warning("MailRail operator notify failed: %s", exc)
    return result


def format_settlement_receipt(
    payer: str,
    amount_usdc: float,
    resource: str,
    tx_hash: str | None = None,
) -> tuple[str, str]:
    """Format an agent/customer receipt for a settled x402 purchase."""
    subject = f"x402 Settlement Receipt: {resource} (${amount_usdc:.4f} USDC)"
    body = (
        f"Payment Settlement Confirmation\n"
        f"-------------------------------\n"
        f"Resource: {resource}\n"
        f"Amount:   ${amount_usdc:.4f} USDC\n"
        f"Payer:    {payer}\n"
        f"Tx Hash:  {tx_hash or 'n/a (testnet/offchain)'}\n"
        f"Network:  {settings.x402_default_network}\n"
        f"\nThank you for using the x402 autonomous agent marketplace."
    )
    return subject, body
 
 
def process_inbound_mail(
    sender: str,
    subject: str,
    body: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ingest and record an inbound message from an external agent or webhook."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    clean_subject = defuse_mentions(subject)
    clean_body = defuse_mentions(body)
    inbound_id = event_key("inbound", sender, clean_subject, clean_body[:50])

    from app.mailrail_agent import AGENT_ID

    inbound_meta = dict(metadata or {})
    inbound_meta.setdefault("agent_id", AGENT_ID)
    record = {
        "ts": now_iso,
        "inbound_id": inbound_id,
        "from": sender,
        "to": settings.mailrail_from_address,
        "subject": clean_subject,
        "body": clean_body,
        "metadata": inbound_meta,
        "status": "received",
    }

    _record_inbound_ledger(record)
    log.info("MailRail ingested inbound mail from %s (inbound_id=%s)", sender, inbound_id)
    result = {
        "status": "received",
        "inbound_id": inbound_id,
        "from": sender,
        "to": settings.mailrail_from_address,
        "subject": clean_subject,
        "timestamp": now_iso,
        "agent_id": inbound_meta.get("agent_id"),
    }
    try:
        from app.mailrail_agent import notify_operator

        result["operator_notify"] = notify_operator(
            f"[MailRail inbound] {clean_subject}",
            f"From: {sender}\n\n{clean_body}",
            event_id=inbound_id,
            already_emailed=False,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("operator notify after inbound failed: %s", exc)
    return result


class AgentMailWebhookError(Exception):
    """Verified-webhook failure. ``code`` is safe to return to the caller."""

    def __init__(self, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


def agentmail_webhook_status() -> dict[str, Any]:
    """Public probe. Says the route exists and whether a signing secret is set."""
    secret = (settings.mailrail_agentmail_webhook_secret or "").strip()
    return {
        "ok": True,
        "accepts": "POST",
        "secret_configured": secret.startswith("whsec_") and len(secret) > len("whsec_"),
    }


def _agentmail_secret_bytes() -> bytes:
    secret = (settings.mailrail_agentmail_webhook_secret or "").strip()
    if not secret.startswith("whsec_"):
        raise AgentMailWebhookError(503, "agentmail_webhook_unconfigured")
    try:
        key = base64.b64decode(secret[len("whsec_") :], validate=True)
    except Exception as exc:
        raise AgentMailWebhookError(503, "agentmail_webhook_unconfigured") from exc
    if not key:
        raise AgentMailWebhookError(503, "agentmail_webhook_unconfigured")
    return key


def _header(headers: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = headers.get(name)
        if value:
            return value.strip()
    return ""


def _agentmail_signature_ok(key: bytes, signed: bytes, signature_header: str) -> bool:
    mac = hmac.new(key, signed, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("ascii")
    for part in signature_header.split():
        version, sep, sig = part.partition(",")
        if sep != "," or version != "v1" or len(sig) != len(expected):
            continue
        if hmac.compare_digest(sig, expected):
            return True
    return False


def verify_agentmail_webhook(
    body: bytes,
    headers: Mapping[str, str],
    *,
    now: float | None = None,
) -> dict[str, Any]:
    """Verify a Svix-signed AgentMail delivery and return the JSON object.

    Fail closed when the secret is missing or not a ``whsec_`` key.
    """
    if len(body) > _AGENTMAIL_MAX_BODY_BYTES:
        raise AgentMailWebhookError(413, "payload_too_large")
    key = _agentmail_secret_bytes()
    msg_id = _header(headers, "svix-id", "webhook-id")
    timestamp = _header(headers, "svix-timestamp", "webhook-timestamp")
    signature = _header(headers, "svix-signature", "webhook-signature")
    if not msg_id or not timestamp or not signature:
        raise AgentMailWebhookError(401, "invalid_signature")
    try:
        sent_at = int(timestamp)
    except ValueError as exc:
        raise AgentMailWebhookError(401, "invalid_signature") from exc
    current = time.time() if now is None else now
    if abs(current - sent_at) > _AGENTMAIL_TOLERANCE_SECONDS:
        raise AgentMailWebhookError(401, "invalid_signature")
    signed = f"{msg_id}.{timestamp}.".encode("utf-8") + body
    if not _agentmail_signature_ok(key, signed, signature):
        raise AgentMailWebhookError(401, "invalid_signature")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentMailWebhookError(400, "invalid_payload") from exc
    if not isinstance(payload, dict):
        raise AgentMailWebhookError(400, "invalid_payload")
    return payload


def _agentmail_address(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    text = str(value or "").strip()
    return text or "unknown@agentmail.to"


def ingest_agentmail_event(event: dict[str, Any]) -> dict[str, Any]:
    """Record ``message.received``. Other event types are acknowledged and ignored."""
    event_type = str(event.get("event_type") or "")
    event_id = str(event.get("event_id") or "")
    if event_type != "message.received":
        return {"ok": True, "status": "ignored", "event_type": event_type, "event_id": event_id}

    message = event.get("message")
    if not isinstance(message, dict):
        raise AgentMailWebhookError(400, "invalid_payload")

    dedup = event_id or str(message.get("message_id") or "")
    dedup_key = f"agentmail:{dedup}" if dedup else ""
    if dedup_key and dedup_key in _SEEN_KEYS:
        return {"ok": True, "status": "duplicate", "event_id": event_id}

    text = message.get("text") or message.get("extracted_text") or message.get("preview") or ""
    if not isinstance(text, str):
        text = str(text)
    subject = message.get("subject") or "(no subject)"
    if not isinstance(subject, str):
        subject = str(subject)
    received = process_inbound_mail(
        sender=_agentmail_address(message.get("from_") or message.get("from")),
        subject=subject,
        body=text,
        metadata={
            "source": "agentmail",
            "event_id": event_id,
            "event_type": event_type,
            "inbox_id": message.get("inbox_id"),
            "message_id": message.get("message_id"),
            "to": message.get("to"),
            "body_omitted": bool(message.get("body_url")) and not message.get("text"),
        },
    )
    if dedup_key:
        _SEEN_KEYS.add(dedup_key)
    return {
        "ok": True,
        "status": "received",
        "event_id": event_id,
        "inbound_id": received.get("inbound_id"),
    }


def handle_agentmail_webhook(body: bytes, headers: Mapping[str, str]) -> dict[str, Any]:
    """Verify one AgentMail delivery and ingest it when it is inbound mail."""
    return ingest_agentmail_event(verify_agentmail_webhook(body, headers))


def get_inbox_messages(limit: int = 50) -> list[dict[str, Any]]:
    """Read recent inbound messages from ledger/mailrail_inbox.jsonl (newest first)."""
    if not MAILRAIL_INBOX_FILE.exists():
        return []
    try:
        lines = MAILRAIL_INBOX_FILE.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in reversed(lines[-limit:]) if line.strip()]
    except Exception as exc:
        log.warning("Failed to read inbox messages: %s", exc)
        return []


def get_outbox_messages(limit: int = 50) -> list[dict[str, Any]]:
    """Read recent outbound messages from ledger/mailrail.jsonl (newest first)."""
    if not MAILRAIL_LEDGER_FILE.exists():
        return []
    try:
        lines = MAILRAIL_LEDGER_FILE.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in reversed(lines[-limit:]) if line.strip()]
    except Exception as exc:
        log.warning("Failed to read outbox messages: %s", exc)
        return []


def get_mailrail_stats() -> dict[str, Any]:
    """Return comprehensive MailRail in/out telemetry and queue status."""
    outbox_count = 0
    if MAILRAIL_LEDGER_FILE.exists():
        try:
            outbox_count = len([line for line in MAILRAIL_LEDGER_FILE.read_text(encoding="utf-8").splitlines() if line.strip()])
        except Exception:
            outbox_count = 0

    inbox_count = 0
    if MAILRAIL_INBOX_FILE.exists():
        try:
            inbox_count = len([line for line in MAILRAIL_INBOX_FILE.read_text(encoding="utf-8").splitlines() if line.strip()])
        except Exception:
            inbox_count = 0

    return {
        "enabled": settings.mailrail_enabled,
        "provider": settings.mailrail_provider,
        "from_address": settings.mailrail_from_address,
        "admin_recipient": settings.mailrail_admin_recipient,
        "outbound_total": outbox_count,
        "inbound_total": inbox_count,
        "dedup_keys_cached": len(_SEEN_KEYS),
        "channels": {
            "resend_active": bool(settings.mailrail_api_key),
            "webhook_active": bool(settings.mailrail_webhook_url),
            "smtp_active": bool(settings.mailrail_smtp_url),
        },
    }


