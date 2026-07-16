"""Fire-and-forget tool invocation events for mission-control SSE."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import UTC, datetime
from typing import Any

HEARTBEAT_INTERVAL_SECONDS = 15

_recent: deque[dict[str, Any]] = deque(maxlen=500)
_subscribers: list[asyncio.Queue[dict[str, Any]]] = []


def emit_tool_event(tool: str, agent_id: str, meta: dict[str, Any]) -> None:
    """Record a tool call; never raise — dashboard must not break MCP tools."""
    try:
        event = {
            "type": "tool",
            "ts": datetime.now(UTC).isoformat(),
            "tool": tool,
            "agent_id": agent_id,
            "meta": meta,
        }
        _recent.append(event)
        for queue in list(_subscribers):
            try:
                queue.put_nowait(event)
            except Exception:
                pass
    except Exception:
        pass


def emit_swarm_step(
    *,
    run_id: str,
    role: str,
    phase: str,
    action: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Emit a swarm phase transition onto the shared tool-event stream.

    Uses agent_id "{role}-{run_id[:8]}" so the dashboard's agent-lanes panel
    (which matches agent_id.startswith(lane) for scout/warden/treasurer/
    archivist/merchant) lights up, while meta.phase drives the swarm panel.
    """
    agent_id = f"{role}-{run_id[:8]}"
    meta = {
        "swarm": True,
        "phase": phase,
        "role": role,
        "run_id": run_id,
        **(detail or {}),
    }
    emit_tool_event(action, agent_id, meta)


def emit_os_alert(*, status: str, previous: str, concerns: list[str]) -> None:
    """Emit a host-OS health-level transition onto the shared event stream.

    Rides the tool-event pipe (same as swarm steps) so existing dashboard
    subscribers see it without a new stream; meta.os_alert marks the kind.
    """
    emit_tool_event(
        "os_monitor",
        "os-monitor",
        {
            "os_alert": True,
            "status": status,
            "previous": previous,
            "concerns": concerns,
        },
    )


def recent_events(limit: int = 200) -> list[dict[str, Any]]:
    items = list(_recent)
    return items[-limit:]


def _heartbeat_event() -> dict[str, Any]:
    return {"type": "heartbeat", "ts": datetime.now(UTC).isoformat()}


async def event_stream():
    """Async generator for SSE subscribers with 15s heartbeats."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _subscribers.append(queue)
    try:
        for item in list(_recent)[-50:]:
            yield item
        while True:
            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=HEARTBEAT_INTERVAL_SECONDS
                )
                yield event
            except asyncio.TimeoutError:
                hb = _heartbeat_event()
                for sub in list(_subscribers):
                    try:
                        sub.put_nowait(hb)
                    except Exception:
                        pass
                yield hb
    finally:
        if queue in _subscribers:
            _subscribers.remove(queue)


def format_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"