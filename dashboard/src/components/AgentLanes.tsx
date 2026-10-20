import type { AgentStats, ToolEvent } from "../types/api";

interface AgentLanesProps {
  agents: AgentStats[];
  events: ToolEvent[];
  density: string;
}

const AGENT_ROLES: Record<string, string> = {
  scout: "Discovers paid services",
  warden: "Budget gatekeeper",
  treasurer: "Executes payments",
  archivist: "Caches responses",
  merchant: "Revenue operations",
};

const AGENT_COLORS: Record<string, string> = {
  scout: "#2775CA",
  warden: "#F5A623",
  treasurer: "#2FBF71",
  archivist: "#8B949E",
  merchant: "#E5484D",
};

function getRole(agentId: string): string {
  for (const [key, role] of Object.entries(AGENT_ROLES)) {
    if (agentId.toLowerCase().includes(key)) return role;
  }
  return "Agent";
}

function getColor(agentId: string): string {
  for (const [key, color] of Object.entries(AGENT_COLORS)) {
    if (agentId.toLowerCase().includes(key)) return color;
  }
  return "#8B949E";
}

export function AgentLanes({ agents, events, density }: AgentLanesProps) {
  // Get last action per agent
  const lastActions: Record<string, ToolEvent> = {};
  for (const e of events) {
    if (e.type === "heartbeat") continue;
    if (!lastActions[e.agent_id] || e.ts > lastActions[e.agent_id].ts) {
      lastActions[e.agent_id] = e;
    }
  }

  // Count calls today per agent
  const today = new Date().toISOString().slice(0, 10);
  const callsToday: Record<string, number> = {};
  for (const e of events) {
    if (e.type === "heartbeat") continue;
    if (e.ts.startsWith(today)) {
      callsToday[e.agent_id] = (callsToday[e.agent_id] || 0) + 1;
    }
  }

  return (
    <div className="panel" style={{ gridColumn: "span 4", minHeight: "200px" }}>
      <div className="panel-title">
        Agent Lanes
        {density === "guided" && (
          <span title="x402 operating group agents and their current status." style={{ cursor: "help", opacity: 0.6 }}>?</span>
        )}
      </div>

      {agents.length === 0 ? (
        <div className="empty-state">
          <span>No agents registered</span>
          <span style={{ fontSize: "12px" }}>Agents appear after their first tool call</span>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {agents.map((agent) => {
            const color = getColor(agent.agent_id);
            const last = lastActions[agent.agent_id];
            return (
              <div
                key={agent.agent_id}
                style={{
                  padding: "8px 10px",
                  borderRadius: "6px",
                  border: `1px solid ${color}22`,
                  background: `${color}08`,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span
                    className="mono"
                    style={{ fontSize: "12px", fontWeight: 600, color }}
                  >
                    {agent.agent_id}
                  </span>
                  <span
                    className="chip"
                    style={{
                      fontSize: "10px",
                      background: agent.tier === "pro" ? "rgba(47, 191, 113, 0.15)" : "rgba(139, 148, 158, 0.15)",
                      color: agent.tier === "pro" ? "var(--color-green)" : "var(--color-text-muted)",
                    }}
                  >
                    {agent.tier}
                  </span>
                </div>
                {density !== "operator" && (
                  <div style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "2px" }}>
                    {getRole(agent.agent_id)}
                  </div>
                )}
                <div style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "4px" }}>
                  {last ? `Last: ${last.tool}` : "No recent calls"} · {callsToday[agent.agent_id] || agent.calls_this_month} calls
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
