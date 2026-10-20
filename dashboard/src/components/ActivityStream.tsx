import { useEffect, useRef, useState } from "react";
import type { ToolEvent } from "../types/api";


interface ActivityStreamProps {
  events: ToolEvent[];
  density: string;
}

const AGENT_COLORS: Record<string, string> = {
  scout: "#2775CA",
  warden: "#F5A623",
  treasurer: "#2FBF71",
  archivist: "#8B949E",
  merchant: "#E5484D",
};

function agentColor(agentId: string): string {
  for (const [key, color] of Object.entries(AGENT_COLORS)) {
    if (agentId.toLowerCase().includes(key)) return color;
  }
  return "#8B949E";
}

export function ActivityStream({ events, density }: ActivityStreamProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (!paused && containerRef.current) {
      containerRef.current.scrollTop = 0;
    }
  }, [events, paused]);

  const displayed = events
    .filter((e) => e.type !== "heartbeat")
    .slice(-200)
    .reverse();

  return (
    <div
      className="panel"
      style={{ gridColumn: "span 8", minHeight: "200px", maxHeight: "360px", display: "flex", flexDirection: "column" }}
    >
      <div className="panel-title">
        Activity Stream
        {density === "guided" && (
          <span title="Live feed of MCP tool calls. Pauses on hover." style={{ cursor: "help", opacity: 0.6 }}>?</span>
        )}
        {paused && (
          <span style={{ fontSize: "10px", color: "var(--color-amber)", marginLeft: "auto" }}>paused</span>
        )}
      </div>

      {displayed.length === 0 ? (
        <div className="empty-state">
          <span>No activity yet</span>
          <span style={{ fontSize: "12px" }}>Tool calls will appear here in real time</span>
        </div>
      ) : (
        <div
          ref={containerRef}
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          style={{ overflow: "auto", flex: 1 }}
          role="log"
          aria-label="Activity stream"
        >
          {displayed.map((event, i) => (
            <div
              key={`${event.ts}-${i}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                padding: "4px 0",
                fontSize: "12px",
                borderBottom: "1px solid var(--color-border)",
              }}
            >
              <span className="mono" style={{ color: "var(--color-text-muted)", fontSize: "11px", flexShrink: 0 }}>
                {new Date(event.ts).toLocaleTimeString("en-US", { hour12: false })}
              </span>
              <span
                className="chip"
                style={{
                  background: `${agentColor(event.agent_id)}22`,
                  color: agentColor(event.agent_id),
                  fontSize: "10px",
                  flexShrink: 0,
                }}
              >
                {event.agent_id.split("-")[0]}
              </span>
              <span className="mono" style={{ fontSize: "12px" }}>
                {event.tool}
              </span>
              <span style={{ marginLeft: "auto", fontSize: "11px", color: "var(--color-text-muted)" }}>
                {density !== "operator" && `quota: ${(event.meta as Record<string, number>).quota_remaining ?? "—"}`}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
