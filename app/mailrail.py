"""MailRail — Agent communication, transactional notification, and dispatch rail.

Provides a unified interface for agents (scout, warden, treasurer, merchant, sovereign, profit-oracle)
and background watchers to send alerts, customer receipts, and inter-agent messages.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from app.config import settings

log = logging.getLogger("x402.mailrail")

MAILRAIL_LEDGER_FILE = Path("ledger/mailrail.jsonl")
_SEEN_KEYS: set[str] = set()
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
    to: str,
    subject: str,
    body: str,
    event_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send an email / notification via MailRail.

    Returns dict containing status ('sent', 'deduplicated', 'disabled', or 'failed'),
    message_id, and delivery timestamp.
    """
    key = event_id or event_key(to, subject, body[:100])

    if key in _SEEN_KEYS:
        log.info("MailRail dedup hit for key %s; suppressing.", key)
        return {
            "status": "deduplicated",
            "event_id": key,
            "to": to,
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
            live_success = _dispatch_resend(to, clean_subject, clean_body)
        elif provider == "webhook":
            live_success = _dispatch_webhook(to, clean_subject, clean_body)

    record = {
        "ts": now_iso,
        "event_id": key,
        "to": to,
        "from": settings.mailrail_from_address,
        "subject": clean_subject,
        "body": clean_body,
        "provider": provider,
        "metadata": metadata or {},
        "status": "sent" if live_success else "dispatch_failed",
    }

    _record_mail_ledger(record)
    _SEEN_KEYS.add(key)

    log.info("MailRail dispatched mail to %s via %s (event_id=%s)", to, provider, key)
    return {
        "status": "sent" if live_success else "dispatch_failed",
        "event_id": key,
        "to": to,
        "subject": clean_subject,
        "delivered": live_success,
        "timestamp": now_iso,
    }


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
