"""AgentMail (MailRail) notifications for US City Network operations.

Every catalog browse, free sample, paid settlement, and MCP city tool call
emits a structured outbound message via ``mailrail.send_agent_mail``. Delivery
is fire-and-forget: failures are logged and never propagate to callers.
"""

from __future__ import annotations

import logging
from typing import Any

from app import mailrail
from app.config import settings

log = logging.getLogger("x402.city_compliance.agentmail")

CityCallKind = str  # catalog | sample | paid_settle | paid_mcp | paid_probe | error


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
) -> str:
    parts = ["city-call", call_kind, channel, city_code or "all", address or "-"]
    if agent_id:
        parts.append(agent_id)
    if tx_hash:
        parts.append(tx_hash)
    return mailrail.event_key(*parts)


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
) -> dict[str, Any] | None:
    """Dispatch AgentMail for one city-network operation. Never raises."""
    try:
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
        )
        return mailrail.send_agent_mail(
            to=_recipient(),
            subject=subject,
            body=body,
            event_id=event_id,
            metadata={
                "product": "us-city-open-data-compliance",
                "call_kind": call_kind,
                "city_code": city_code,
                "channel": channel,
                "agent_id": agent_id,
            },
        )
    except Exception as exc:  # noqa: BLE001 — must not break city product paths
        log.warning("City AgentMail dispatch failed (%s/%s): %s", call_kind, city_code, exc)
        return None


def verdict_from_report(report: dict[str, Any] | None) -> str | None:
    if not report:
        return None
    return report.get("compliance_verdict") or report.get("verdict")
