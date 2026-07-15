import type { SwarmProduct } from "../api/client";
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
};

const LANES = ["scout", "warden", "treasurer", "archivist", "merchant"] as const;

const PHASE_COLOR: Record<string, string> = {
  scouting: "var(--base)",
  approved: "var(--green)",
  vetoed: "var(--red)",
  buying: "var(--usdc)",
  composing: "var(--amber)",
  listing: "var(--base)",
  selling: "var(--green)",
  failed: "var(--red)",
};

function isSwarm(e: StreamEvent): boolean {
  return (e.meta as SwarmMeta | undefined)?.swarm === true;
}

function describe(e: StreamEvent): string {
  const m = (e.meta ?? {}) as SwarmMeta;
  switch (m.phase) {
    case "scouting":
      return `found ${m.found ?? 0} upstream service(s)`;
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
    case "failed":
      return `run failed — ${m.reason ?? "error"}`;
    default:
      return e.tool ?? "";
  }
}

export function SwarmActivity({
  events,
  products,
}: {
  events: StreamEvent[];
  products: SwarmProduct[];
}) {
  const swarmEvents = events.filter(isSwarm);
  const counts = Object.fromEntries(LANES.map((l) => [l, 0])) as Record<string, number>;
  for (const e of swarmEvents) {
    const role = (e.meta as SwarmMeta).role;
    if (role && role in counts) counts[role] += 1;
  }

  const totalMargin = products.reduce((n, p) => n + p.revenue_usdc, 0);

  return (
    <section id="panel-swarm" className="panel" style={{ gridColumn: "span 12" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>Swarm Agency — buy → compose → sell</h3>
        <span className="mono" style={{ color: "var(--text-muted)", fontSize: 12 }}>
          {products.length} listed · ${totalMargin.toFixed(2)} realized
        </span>
      </div>

      {/* Pipeline lanes */}
      <div style={{ display: "flex", gap: 8, margin: "12px 0", flexWrap: "wrap" }}>
        {LANES.map((lane, i) => (
          <div key={lane} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: "6px 10px",
                minWidth: 84,
                textAlign: "center",
                opacity: counts[lane] ? 1 : 0.5,
              }}
            >
              <div style={{ fontSize: 11, textTransform: "uppercase", color: "var(--text-muted)" }}>
                {lane}
              </div>
              <div className="mono" style={{ fontSize: 18 }}>{counts[lane]}</div>
            </div>
            {i < LANES.length - 1 && <span style={{ color: "var(--text-muted)" }}>→</span>}
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {/* Live phase feed */}
        <div style={{ flex: "1 1 340px", minWidth: 300 }}>
          <h4 style={{ margin: "0 0 8px" }}>Live activity</h4>
          {swarmEvents.length === 0 ? (
            <div style={{ color: "var(--text-muted)", fontSize: 14 }}>
              No swarm runs yet. Call <code className="mono">run_swarm_research</code> via MCP.
            </div>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, maxHeight: 260, overflow: "auto" }}>
              {swarmEvents.map((e, i) => {
                const m = (e.meta ?? {}) as SwarmMeta;
                return (
                  <li key={i} className="mono" style={{ fontSize: 12, marginBottom: 6, display: "flex", gap: 8 }}>
                    <span style={{ color: "var(--text-muted)", whiteSpace: "nowrap" }} title={e.ts}>
                      {relativeTime(e.ts)}
                    </span>
                    <span
                      style={{
                        color: PHASE_COLOR[m.phase ?? ""] ?? "var(--text-muted)",
                        fontWeight: 600,
                        textTransform: "uppercase",
                        minWidth: 72,
                      }}
                    >
                      {m.role ?? m.phase}
                    </span>
                    <span>{describe(e)}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Listed products with margin */}
        <div style={{ flex: "1 1 340px", minWidth: 300 }}>
          <h4 style={{ margin: "0 0 8px" }}>Composite products</h4>
          {products.length === 0 ? (
            <div style={{ color: "var(--text-muted)", fontSize: 14 }}>
              Composites appear here once the merchant lists them.
            </div>
          ) : (
            <table className="mono" style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ color: "var(--text-muted)", textAlign: "left" }}>
                  <th>Topic</th>
                  <th>Cost</th>
                  <th>Price</th>
                  <th>Margin</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr key={p.product_id} style={{ borderTop: "1px solid var(--border)" }}>
                    <td title={p.sources.join(", ")}>{p.topic}</td>
                    <td>${p.cost_basis_usdc.toFixed(4)}</td>
                    <td>${p.price_usdc.toFixed(2)}</td>
                    <td style={{ color: "var(--green)" }}>${p.margin_usdc.toFixed(2)}</td>
                    <td style={{ color: p.status === "sold" ? "var(--green)" : "var(--amber)" }}>
                      {p.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  );
}
