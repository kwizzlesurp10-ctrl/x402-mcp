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
from urllib.parse import quote

from app.config import settings

log = logging.getLogger("x402.mailrail")

MAILRAIL_LEDGER_FILE = Path("ledger/mailrail.jsonl")
MAILRAIL_INBOX_FILE = Path("ledger/mailrail_inbox.jsonl")
_SEEN_KEYS: set[str] = set()
_MENTION_RE = re.compile(r"(?<![\w.-])@([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)")


# smtp and file are not senders. Resend, webhook, and agentmail are the transports.
SELECTABLE_PROVIDERS = frozenset({"mock", "resend", "webhook", "agentmail"})
REAL_TRANSPORTS = frozenset({"resend", "webhook", "agentmail"})
LEDGER_ONLY_DOCTOR_MESSAGE = (
    "MailRail ledger only, ephemeral debug log (ledger/mailrail.jsonl). "
    "Restart-volatile; not stored in Redis."
)


def normalize_provider(raw: str | None) -> str:
    """Return a selectable provider, or ``unsupported`` for smtp, file, and anything else."""
    provider = (raw or "mock").strip().lower()
    if provider in SELECTABLE_PROVIDERS:
        return provider
    return "unsupported"


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


def _dispatch_agentmail(to: str, subject: str, body: str) -> bool:
    """Dispatch via AgentMail send API."""
    from app.mailrail_agentmail import AGENTMAIL_SEND_API, resolve_inbox_id

    api_key = settings.mailrail_api_key
    if not api_key:
        log.warning("AgentMail requested but MAILRAIL_API_KEY is not set.")
        return False
    inbox_id = resolve_inbox_id()
    if not inbox_id:
        log.warning("AgentMail requested but inbox id / from address is empty.")
        return False
    try:
        import httpx

        url = AGENTMAIL_SEND_API.format(inbox_id=quote(inbox_id, safe=""))
        res = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "to": to,
                "subject": subject,
                "text": body,
            },
            timeout=15.0,
        )
        if res.status_code not in (200, 201):
            log.warning(
                "AgentMail dispatch failed: status=%s body=%s",
                res.status_code,
                res.text[:500],
            )
            return False
        return True
    except Exception as e:
        log.warning("AgentMail dispatch failed: %s", e)
        return False


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


def _transport_result(provider: str, recipient: str, subject: str, body: str) -> tuple[str, bool]:
    """Dispatch on a real transport, or report the send as not delivered.

    ``mock`` and any provider that is not resend, webhook, or agentmail record a debug line
    and return ``disabled`` / not delivered. Resend, webhook, and agentmail report
    delivered only after a successful HTTP response.
    """
    if not settings.mailrail_enabled or provider not in REAL_TRANSPORTS:
        return "disabled", False
    if provider == "resend":
        ok = _dispatch_resend(recipient, subject, body)
    elif provider == "agentmail":
        ok = _dispatch_agentmail(recipient, subject, body)
    elif provider == "webhook":
        ok = _dispatch_webhook(recipient, subject, body)
    else:
        ok = False
    if ok:
        return "sent", True
    return "dispatch_failed", False


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

    provider = normalize_provider(settings.mailrail_provider)
    status, live_success = _transport_result(provider, recipient, clean_subject, clean_body)

    record = {
        "ts": now_iso,
        "event_id": key,
        "to": recipient,
        "from": settings.mailrail_from_address,
        "subject": clean_subject,
        "body": clean_body,
        "provider": provider,
        "metadata": meta,
        "status": status,
    }

    _record_mail_ledger(record)
    _SEEN_KEYS.add(key)

    log.info(
        "MailRail recorded mail to %s via %s status=%s (event_id=%s)",
        recipient,
        provider,
        status,
        key,
    )
    result = {
        "status": status,
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


def receipt_recipient() -> str:
    """Operator address for a settlement receipt.

    ``MAILRAIL_ADMIN_RECIPIENT`` wins. An empty admin recipient uses
    ``contact_email``.
    """
    admin = (settings.mailrail_admin_recipient or "").strip()
    if admin:
        return admin
    return (settings.contact_email or "").strip()


def _wire_amount_text(
    amount: Any,
    network: str | None = None,
    asset: str | None = None,
) -> str:
    """Decimal USDC text from an atomic wire amount, or ``n/a``.

    Uses ``atomic_to_units``, the same conversion the revenue path uses when
    it records a settled charge. A non-integer or missing amount is not
    guessed into a dollar figure.
    """
    from app.x402_services import atomic_to_units

    figure = atomic_to_units(amount, network, asset)
    if figure is None:
        return "n/a"
    return f"{figure:.6f}".rstrip("0").rstrip(".")


def format_settlement_receipt(
    payer: str,
    amount: Any,
    resource: str,
    tx_hash: str | None = None,
    *,
    network: str | None = None,
    asset: str | None = None,
) -> tuple[str, str]:
    """Format an agent/customer receipt for a settled x402 purchase."""
    if isinstance(amount, (int, float)) and not isinstance(amount, bool) and network is None and asset is None:
        amount_text = f"{float(amount):.4f}"
    else:
        amount_text = _wire_amount_text(amount, network, asset)
    subject = f"x402 Settlement Receipt: {resource} (${amount_text} USDC)"
    body = (
        f"Payment Settlement Confirmation\n"
        f"-------------------------------\n"
        f"Resource: {resource}\n"
        f"Amount:   ${amount_text} USDC\n"
        f"Payer:    {payer}\n"
        f"Tx Hash:  {tx_hash or 'n/a (testnet/offchain)'}\n"
        f"Network:  {network or settings.x402_default_network}\n"
        f"\nThank you for using the x402 autonomous agent marketplace."
    )
    return subject, body


def dispatch_settlement_receipt(
    *,
    payer: str,
    amount: Any,
    resource: str,
    tx_hash: str | None = None,
    network: str | None = None,
    asset: str | None = None,
) -> dict[str, Any]:
    """Address and record one settlement receipt.

    Empty ``MAILRAIL_ADMIN_RECIPIENT`` sends the receipt to ``contact_email``.
    """
    subject, body = format_settlement_receipt(
        payer,
        amount,
        resource,
        tx_hash,
        network=network,
        asset=asset,
    )
    return send_agent_mail(
        to=receipt_recipient(),
        subject=subject,
        body=body,
        event_id=(str(tx_hash) if tx_hash else None),
        metadata={"kind": "settlement-receipt"},
    )
 
 
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
    """Return MailRail in/out counts from the restart-volatile JSONL debug log."""
    provider_name = normalize_provider(settings.mailrail_provider)
    outbox_count = 0
    if MAILRAIL_LEDGER_FILE.exists():
        try:
            with MAILRAIL_LEDGER_FILE.open("r", encoding="utf-8") as f:
                outbox_count = sum(1 for _ in f)
        except Exception:
            pass

    inbox_count = 0
    if MAILRAIL_INBOX_FILE.exists():
        try:
            with MAILRAIL_INBOX_FILE.open("r", encoding="utf-8") as f:
                inbox_count = sum(1 for _ in f)
        except Exception:
            pass

    return {
        "enabled": settings.mailrail_enabled,
        "provider": settings.mailrail_provider,
        "from_address": settings.mailrail_from_address,
        "admin_recipient": settings.mailrail_admin_recipient,
        "outbound_total": outbox_count,
        "inbound_total": inbox_count,
        "dedup_keys_cached": len(_SEEN_KEYS),
        "channels": {
            "resend_active": provider_name == "resend" and bool(settings.mailrail_api_key),
            "agentmail_active": provider_name == "agentmail" and bool(settings.mailrail_api_key),
            "agentmail_webhook_active": bool(settings.mailrail_agentmail_webhook_secret),
            "webhook_active": provider_name == "webhook" and bool(settings.mailrail_webhook_url),
            "smtp_active": False,
        },
    }


