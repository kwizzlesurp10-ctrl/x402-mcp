import type { SwarmProduct, SwarmRevenue } from "../api/client";
import type { StreamEvent } from "../hooks/useSSE";
import { relativeTime } from "../utils/time";

type SwarmMeta = {
  swarm?: boolean;
  phase?: string;
  role?: string;
  run_id?: string;
  url?: string;
  amount_usdc?: number;
  price_usdc?: number;
  margin_usdc?: number;
  cost_basis_usdc?: number;
  reason?: string;
  settled?: boolean;
  found?: number;
  ltv_cac_projected?: number;
  target_ltv_cac?: number;
};

const AGENT_PIPELINE = [
  { role: "scout", label: "Scout Agent", step: "1. Discover", color: "var(--agent-scout)", desc: "Probes upstream x402 endpoints", icon: "🔍" },
  { role: "warden", label: "Warden Agent", step: "2. Policy Guard", color: "var(--agent-warden)", desc: "Enforces budget & spend limits", icon: "🛡️" },
  { role: "treasurer", label: "Treasurer Agent", step: "3. EVM Vault", color: "var(--agent-treasurer)", desc: "Executes pay_and_fetch payments", icon: "⚡" },
  { role: "archivist", label: "Archivist Agent", step: "4. Cache Layer", color: "var(--agent-archivist)", desc: "Caches raw & composite bundles", icon: "📦" },
  { role: "sovereign", label: "Sovereign Agent", step: "5. Pricing Engine", color: "var(--agent-sovereign)", desc: "Calculates margin floors & markup", icon: "⚖️" },
  { role: "merchant", label: "Merchant Agent", step: "6. Resale Listing", color: "var(--agent-merchant)", desc: "Publishes composite listings", icon: "🏪" },
] as const;

const PHASE_COLOR: Record<string, string> = {
  scouting: "var(--agent-scout)",
  approved: "var(--green)",
  vetoed: "var(--red)",
  buying: "var(--agent-treasurer)",
  composing: "var(--amber)",
  listing: "var(--agent-merchant)",
  selling: "var(--green)",
  optimizing: "var(--green)",
  failed: "var(--red)",
};

function isSwarm(e: StreamEvent): boolean {
  return (e.meta as SwarmMeta | undefined)?.swarm === true;
}

function describe(e: StreamEvent): string {
  const m = (e.meta ?? {}) as SwarmMeta;
  switch (m.phase) {
    case "scouting":
      return `scouted ${m.found ?? 0} upstream service(s)`;
    case "approved":
      return `approved ${m.url ?? ""} @ $${(m.amount_usdc ?? 0).toFixed(4)}`;
    case "vetoed":
      return `vetoed ${m.url ?? ""} — ${m.reason ?? ""}`;
    case "buying":
      return `paid $${(m.amount_usdc ?? 0).toFixed(4)}${m.settled ? " ✓ settled" : ""} → ${m.url ?? ""}`;
    case "composing":
      return `composed product · cost $${(m.cost_basis_usdc ?? 0).toFixed(4)} → price $${(m.price_usdc ?? 0).toFixed(2)}`;
    case "listing":
      return `listed composite @ $${(m.price_usdc ?? 0).toFixed(2)}`;
    case "selling":
      return `SOLD · +$${(m.price_usdc ?? m.margin_usdc ?? 0).toFixed(2)} revenue`;
    case "optimizing":
      return `optimized → $${(m.price_usdc ?? 0).toFixed(2)} · LTV:CAC ${(m.ltv_cac_projected ?? 0).toFixed(1)}`;
    case "failed":
      return `run failed — ${m.reason ?? "error"}`;
    default:
      return e.tool ?? "";
  }
}

export function SwarmActivity({
  events,
  products,
  revenue,
}: {
  events: StreamEvent[];
  products: SwarmProduct[];
  revenue?: SwarmRevenue;
}) {
  const swarmEvents = events.filter(isSwarm);
  const counts = Object.fromEntries(AGENT_PIPELINE.map((a) => [a.role, 0])) as Record<string, number>;
  for (const e of swarmEvents) {
    const role = (e.meta as SwarmMeta).role;
    if (role && role in counts) counts[role] += 1;
  }

  const totalMargin = products.reduce((n, p) => n + p.revenue_usdc, 0);

  return (
    <section id="panel-swarm" className="panel" style={{ gridColumn: "span 12" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 20, color: "#fff", display: "flex", alignItems: "center", gap: 10 }}>
            <span className="pulsing-dot" style={{ background: "var(--neon-cyan)" }} /> Swarm Pipeline Agents — Buy ➔ Compose ➔ Resell
          </h3>
          <p style={{ margin: "6px 0 0", color: "var(--text-muted)", fontSize: 13 }}>
            6 Autonomous Subagents operating cost-basis pricing & x402 revenue reselling
          </p>
        </div>
        <div style={{ textAlign: "right", background: "rgba(16, 185, 129, 0.08)", padding: "8px 16px", borderRadius: 10, border: "1px solid rgba(16, 185, 129, 0.2)" }}>
          <div className="mono" style={{ color: "var(--green)", fontWeight: 700, fontSize: 18 }}>
            +${totalMargin.toFixed(2)} Realized
          </div>
          <div className="mono" style={{ color: "var(--text-muted)", fontSize: 12 }}>
            {products.length} product(s) in catalog
          </div>
        </div>
      </div>

      {/* 6-Agent Swarm Pipeline Flow Topology Visualization */}
      <div
        style={{
          marginBottom: 20,
          padding: "20px 16px",
          background: "rgba(6, 9, 14, 0.6)",
          borderRadius: 14,
          border: "1px solid rgba(255, 255, 255, 0.06)",
          backdropFilter: "blur(12px)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
          {AGENT_PIPELINE.map((agent, idx) => {
            const activityCount = counts[agent.role] || 0;
            const isActive = activityCount > 0;
            return (
              <div key={agent.role} style={{ display: "flex", alignItems: "center", flex: "1 1 150px", minWidth: 150 }}>
                <div
                  style={{
                    width: "100%",
                    padding: "14px 12px",
                    background: isActive ? `linear-gradient(135deg, ${agent.color}15 0%, rgba(15,23,36,0.8) 100%)` : "rgba(15, 23, 36, 0.4)",
                    borderRadius: 12,
                    border: `1px solid ${isActive ? agent.color : "rgba(255,255,255,0.08)"}`,
                    boxShadow: isActive ? `0 0 16px ${agent.color}33, inset 0 1px 1px ${agent.color}44` : "none",
                    transition: "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
                    position: "relative",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span className="mono" style={{ fontSize: 10, color: agent.color, textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.05em" }}>
                      {agent.step}
                    </span>
                    <span
                      className="mono"
                      style={{
                        fontSize: 10,
                        background: isActive ? `${agent.color}33` : "rgba(255,255,255,0.06)",
                        color: isActive ? agent.color : "var(--text-muted)",
                        padding: "2px 7px",
                        borderRadius: 12,
                        fontWeight: 600,
                        border: `1px solid ${isActive ? agent.color : "transparent"}`,
                      }}
                    >
                      {activityCount} ops
                    </span>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: "#fff", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>{agent.icon}</span>
                    <span>{agent.label}</span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.3 }}>
                    {agent.desc}
                  </div>
                </div>
                {idx < AGENT_PIPELINE.length - 1 && (
                  <div className="hide-mobile" style={{ display: "flex", alignItems: "center", padding: "0 4px", color: "rgba(255,255,255,0.2)", fontSize: 14 }}>
                    ➔
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Revenue Intelligence Metrics Card */}
      {revenue && (
        <div
          className="mono"
          style={{
            display: "flex",
            gap: 24,
            flexWrap: "wrap",
            alignItems: "center",
            marginBottom: 20,
            padding: "14px 18px",
            background: "linear-gradient(90deg, rgba(0, 82, 255, 0.1) 0%, rgba(0, 240, 255, 0.05) 100%)",
            border: "1px solid rgba(0, 240, 255, 0.2)",
            borderRadius: 12,
            fontSize: 13,
            boxShadow: "0 4px 20px rgba(0,0,0,0.2)",
          }}
        >
          <span style={{ textTransform: "uppercase", color: "var(--neon-cyan)", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--neon-cyan)" }} /> Swarm composites
          </span>
          <span>
            Swarm spend: <strong style={{ color: "var(--red)" }}>${revenue.total_spend_usdc.toFixed(4)}</strong>
          </span>
          <span>
            Swarm revenue: <strong style={{ color: "var(--green)" }}>${revenue.total_revenue_usdc.toFixed(4)}</strong>
          </span>
          <span>
            Swarm margin: <strong style={{ color: "var(--neon-cyan)", fontSize: 14 }}>${revenue.realized_margin_usdc.toFixed(4)}</strong>
          </span>
          <span>
            {revenue.listed_count} listed · {revenue.sold_count} sold
          </span>
          {revenue.storefront && (
            <span title={revenue.note ?? "Full settled ledger, including first-party SKUs"}>
              Storefront: <strong style={{ color: "var(--green)" }}>${revenue.storefront.revenue_usdc.toFixed(4)}</strong>
              <span style={{ color: "var(--text-muted)", fontSize: 11 }}>
                {" "}({revenue.storefront.external_usdc.toFixed(4)} external)
              </span>
            </span>
          )}
          <span>
            LTV:CAC Ratio:{" "}
            <strong
              style={{
                color: revenue.ltv_cac != null && revenue.ltv_cac >= revenue.target_ltv_cac ? "var(--green)" : "var(--amber)",
                background: "rgba(255,255,255,0.06)",
                padding: "2px 8px",
                borderRadius: 6,
              }}
            >
              {revenue.ltv_cac?.toFixed(1) ?? "N/A"}
            </strong>{" "}
            <span style={{ color: "var(--text-muted)", fontSize: 11 }}>(target {revenue.target_ltv_cac})</span>
          </span>
        </div>
      )}

      {/* Real-time Swarm Events Stream */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
            Live Agent Pipeline Feed ({swarmEvents.length} events)
          </span>
        </div>
        {swarmEvents.length === 0 ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "24px 0", textAlign: "center", background: "rgba(0,0,0,0.2)", borderRadius: 8, border: "1px dashed rgba(255,255,255,0.08)" }}>
            No swarm pipeline events logged yet. Trigger a run with <code className="mono" style={{ color: "var(--neon-cyan)" }}>run_swarm_research</code>.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 240, overflowY: "auto", paddingRight: 4 }}>
            {swarmEvents.map((e, idx) => {
              const m = (e.meta ?? {}) as SwarmMeta;
              const color = PHASE_COLOR[m.phase ?? ""] ?? "var(--text-muted)";
              return (
                <div
                  key={idx}
                  className="mono"
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 12px",
                    background: "rgba(0,0,0,0.35)",
                    borderLeft: `4px solid ${color}`,
                    borderRadius: 6,
                    fontSize: 12,
                    transition: "background 0.2s ease",
                  }}
                >
                  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                    <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{relativeTime(e.ts)}</span>
                    <span
                      style={{
                        color,
                        fontWeight: 700,
                        textTransform: "uppercase",
                        fontSize: 10,
                        background: `${color}22`,
                        padding: "2px 8px",
                        borderRadius: 4,
                        border: `1px solid ${color}44`,
                      }}
                    >
                      {m.role ?? "agent"} :: {m.phase ?? "event"}
                    </span>
                    <span style={{ color: "#e2e8f0" }}>{describe(e)}</span>
                  </div>
                  {m.price_usdc && (
                    <span style={{ color: "var(--green)", fontWeight: 700, fontSize: 13 }}>
                      ${m.price_usdc.toFixed(2)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
