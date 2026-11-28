"""AgentMail (MailRail) notifications for US City Network operations.

Every catalog browse, free sample, paid settlement, and MCP city tool call
emits a structured outbound message via ``mailrail.send_agent_mail``. Delivery
is fire-and-forget: failures are logged and never propagate to callers.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app import mailrail
from app.config import settings

log = logging.getLogger("x402.city_compliance.agentmail")

CityCallKind = str  # catalog | sample | paid_settle | paid_mcp | paid_probe | error

# Non-mock providers coalesce this many city alerts into one outbound send.
_CITY_BATCH_SIZE = 2
_CITY_BATCH: list[dict[str, Any]] = []


def reset_city_batch() -> None:
    """Drop buffered city alerts. Tests call this so batches do not leak."""
    _CITY_BATCH.clear()


def _batches_city_alerts() -> bool:
    """Mock keeps one debug line per call. Every other provider is batched."""
    return (settings.mailrail_provider or "mock").strip().lower() != "mock"


def _recipient() -> str:
    return settings.mailrail_admin_recipient or settings.mailrail_from_address


def format_city_call_alert(
    call_kind: CityCallKind,
    *,
    city_code: str | None = None,
    city_name: str | None = None,
    state: str | None = None,
    address: str | None = None,
    channel: str = "http",
    agent_id: str | None = None,
    price: str | None = None,
    verdict: str | None = None,
    paid: bool | None = None,
    tx_hash: str | None = None,
    payer: str | None = None,
    detail: str | None = None,
) -> tuple[str, str]:
    """Build subject + body for a city-network AgentMail alert."""
    city_label = city_code or "network"
    if city_name and state:
        city_label = f"{city_name}, {state} ({city_code})"
    elif city_code:
        city_label = city_code

    subject = f"[City Network] {call_kind}: {city_label}"
    if paid is True:
        subject += " (paid)"
    elif paid is False:
        subject += " (probe)"

    lines = [
        "US City Open-Data Compliance Network",
        "------------------------------------",
        f"Call kind:  {call_kind}",
        f"Channel:    {channel}",
    ]
    if city_code:
        lines.append(f"City code:  {city_code}")
    if city_name:
        lines.append(f"City:       {city_name}, {state or '?'}")
    if address:
        lines.append(f"Address:    {address}")
    if agent_id:
        lines.append(f"Agent ID:   {agent_id}")
    if price:
        lines.append(f"Price:      {price}")
    if verdict:
        lines.append(f"Verdict:    {verdict}")
    if payer:
        lines.append(f"Payer:      {payer}")
    if tx_hash:
        lines.append(f"Tx hash:    {tx_hash}")
    if detail:
        lines.append(f"Detail:     {detail}")
    lines.append(f"Network:    {settings.x402_default_network}")
    return subject, "\n".join(lines)


def _event_id(
    call_kind: CityCallKind,
    *,
    city_code: str | None = None,
    address: str | None = None,
    channel: str = "http",
    agent_id: str | None = None,
    tx_hash: str | None = None,
    request_id: str | None = None,
) -> str:
    """Build a MailRail dedup key.

    Paid settlements and explicit ``request_id`` values are stable across retries
    of the same request. All other calls include a per-invocation nonce so each
    catalog browse, sample, or probe emits its own alert.
    """
    city = city_code or "all"
    addr = address or "-"
    if tx_hash:
        return mailrail.event_key("city-call", call_kind, channel, city, addr, tx_hash)
    if request_id:
        return mailrail.event_key("city-call", call_kind, channel, city, request_id)
    nonce = time.time_ns()
    parts = ["city-call", call_kind, channel, city, addr, nonce]
    if agent_id:
        parts.append(agent_id)
    return mailrail.event_key(*parts)


def _city_mail_item(
    call_kind: CityCallKind,
    *,
    city_code: str | None = None,
    city_name: str | None = None,
    state: str | None = None,
    address: str | None = None,
    channel: str = "http",
    agent_id: str | None = None,
    price: str | None = None,
    verdict: str | None = None,
    paid: bool | None = None,
    tx_hash: str | None = None,
    payer: str | None = None,
    detail: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    subject, body = format_city_call_alert(
        call_kind,
        city_code=city_code,
        city_name=city_name,
        state=state,
        address=address,
        channel=channel,
        agent_id=agent_id,
        price=price,
        verdict=verdict,
        paid=paid,
        tx_hash=tx_hash,
        payer=payer,
        detail=detail,
    )
    event_id = _event_id(
        call_kind,
        city_code=city_code,
        address=address,
        channel=channel,
        agent_id=agent_id,
        tx_hash=tx_hash,
        request_id=request_id,
    )
    return {
        "to": _recipient(),
        "subject": subject,
        "body": body,
        "event_id": event_id,
        "metadata": {
            "product": "us-city-open-data-compliance",
            "call_kind": call_kind,
            "city_code": city_code,
            "channel": channel,
            "agent_id": agent_id,
        },
    }


def _flush_city_batch() -> dict[str, Any]:
    """Send one message covering every alert waiting in the batch."""
    batch = list(_CITY_BATCH)
    _CITY_BATCH.clear()
    subject = f"[City Network] batch ({len(batch)})"
    body = "\n\n".join(f"{item['subject']}\n{item['body']}" for item in batch)
    event_id = mailrail.event_key("city-batch", *[item["event_id"] for item in batch])
    return mailrail.send_agent_mail(
        to=batch[0]["to"],
        subject=subject,
        body=body,
        event_id=event_id,
        metadata={
            "product": "us-city-open-data-compliance",
            "call_kind": "batch",
            "count": len(batch),
        },
    )


def notify_city_call(
    call_kind: CityCallKind,
    *,
    city_code: str | None = None,
    city_name: str | None = None,
    state: str | None = None,
    address: str | None = None,
    channel: str = "http",
    agent_id: str | None = None,
    price: str | None = None,
    verdict: str | None = None,
    paid: bool | None = None,
    tx_hash: str | None = None,
    payer: str | None = None,
    detail: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any] | None:
    """Dispatch AgentMail for one city-network operation. Never raises.

    ``mock`` writes one debug line per call. Any other provider buffers alerts
    and sends one transport message per ``_CITY_BATCH_SIZE`` calls.
    """
    if call_kind == "error" and detail == "unknown_city":
        return {
            "status": "ignored",
            "delivered": False,
            "detail": "unknown_city",
        }
    try:
        item = _city_mail_item(
            call_kind,
            city_code=city_code,
            city_name=city_name,
            state=state,
            address=address,
            channel=channel,
            agent_id=agent_id,
            price=price,
            verdict=verdict,
            paid=paid,
            tx_hash=tx_hash,
            payer=payer,
            detail=detail,
            request_id=request_id,
        )
        if not _batches_city_alerts():
            return mailrail.send_agent_mail(
                to=item["to"],
                subject=item["subject"],
                body=item["body"],
                event_id=item["event_id"],
                metadata=item["metadata"],
            )
        if any(pending["event_id"] == item["event_id"] for pending in _CITY_BATCH):
            return {
                "status": "deduplicated",
                "delivered": False,
                "event_id": item["event_id"],
            }
        _CITY_BATCH.append(item)
        if len(_CITY_BATCH) < _CITY_BATCH_SIZE:
            return {
                "status": "batched",
                "delivered": False,
                "event_id": item["event_id"],
            }
        return _flush_city_batch()
    except Exception as exc:  # noqa: BLE001 — must not break city product paths
        log.warning("City AgentMail dispatch failed (%s/%s): %s", call_kind, city_code, exc)
        return None


def verdict_from_report(report: dict[str, Any] | None) -> str | None:
    if not report:
        return None
    return report.get("verdict") or report.get("compliance_verdict")
