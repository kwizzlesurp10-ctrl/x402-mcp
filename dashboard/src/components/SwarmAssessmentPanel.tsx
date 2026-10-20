import { useState } from "react";
import type { SwarmAssessment } from "../api/client";
import {
  backlogStatusColor,
  routeScoreColor,
  splitBacklog,
  topProfitRoutes,
} from "../utils/swarmAssessment";
import { relativeTime } from "../utils/time";

type Density = "guided" | "standard" | "operator";

function BacklogRow({ item, compact }: { item: SwarmAssessment["backlog"][number]; compact?: boolean }) {
  return (
    <li
      style={{
        marginBottom: compact ? 6 : 10,
        padding: compact ? "6px 10px" : "8px 12px",
        background: "rgba(0,0,0,0.25)",
        borderRadius: 8,
        border: "1px solid rgba(255,255,255,0.06)",
        listStyle: "none",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
        <strong style={{ fontSize: compact ? 12 : 13 }}>{item.title}</strong>
        <span
          className="mono"
          style={{
            fontSize: 10,
            textTransform: "uppercase",
            color: backlogStatusColor(item.status),
            background: "rgba(255,255,255,0.05)",
            padding: "2px 6px",
            borderRadius: 4,
            whiteSpace: "nowrap",
          }}
        >
          {item.status}
        </span>
      </div>
      {!compact && (
        <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--text-muted)", lineHeight: 1.4 }}>
          {item.detail}
        </p>
      )}
    </li>
  );
}

export function SwarmAssessmentPanel({
  assessment,
  density,
}: {
  assessment: SwarmAssessment | null;
  density: Density;
}) {
  const [humanGatedOpen, setHumanGatedOpen] = useState(false);

  if (!assessment) {
    return (
      <section id="panel-swarm-assessment" className="panel" style={{ gridColumn: "span 12" }}>
        <h3>Strategic assessment</h3>
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading assessor signals…</p>
      </section>
    );
  }

  const { actionable, humanGated } = splitBacklog(assessment.backlog);
  const top = assessment.recommended_route;
  const routes = density === "operator" ? assessment.profit_routes : topProfitRoutes(assessment, density === "guided" ? 1 : 3);

  const compact = density !== "operator";

  return (
    <section id="panel-swarm-assessment" className="panel" style={{ gridColumn: "span 12" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap", marginBottom: compact ? 12 : 16 }}>
        <div>
          <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
            <span className="pulsing-dot" style={{ background: "var(--neon-cyan)" }} />
            Strategic assessment
          </h3>
          <p style={{ margin: "6px 0 0", color: "var(--text-muted)", fontSize: 12 }}>
            Profit routes scored from live repo signals · updated {relativeTime(assessment.generated_at)}
          </p>
        </div>
        {density !== "guided" && (
          <div
            className="mono"
            style={{
              padding: "8px 14px",
              borderRadius: 10,
              background: "linear-gradient(90deg, rgba(0, 82, 255, 0.12) 0%, rgba(0, 240, 255, 0.08) 100%)",
              border: "1px solid rgba(0, 240, 255, 0.25)",
              fontSize: 12,
            }}
          >
            {assessment.signals.mcp_tools as number} tools · head {String(assessment.signals.head ?? "—")}
          </div>
        )}
      </div>

      <div
        style={{
          marginBottom: compact ? 12 : 18,
          padding: compact ? "12px 14px" : "16px 18px",
          borderRadius: 12,
          background: "linear-gradient(135deg, rgba(0, 240, 255, 0.08) 0%, rgba(15, 23, 42, 0.6) 100%)",
          border: "1px solid rgba(0, 240, 255, 0.2)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <div>
            <div className="mono" style={{ fontSize: 10, color: "var(--neon-cyan)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
              Top route
            </div>
            <div style={{ fontSize: compact ? 15 : 17, fontWeight: 700, color: "#fff", marginTop: 4 }}>
              {top.name}
            </div>
          </div>
          <div
            className="mono"
            style={{
              fontSize: compact ? 20 : 24,
              fontWeight: 800,
              color: routeScoreColor(top.priority_score),
            }}
          >
            {top.priority_score.toFixed(1)}
          </div>
        </div>
        {density !== "guided" && (
          <>
            <p style={{ margin: "10px 0 0", fontSize: 12, color: "var(--text-muted)", lineHeight: 1.45 }}>
              {top.why}
            </p>
            <p style={{ margin: "8px 0 0", fontSize: 12, color: "#e2e8f0" }}>
              <strong style={{ color: "var(--neon-cyan)" }}>Next:</strong> {top.next_action}
            </p>
          </>
        )}
      </div>

      {density !== "guided" && routes.length > 1 && (
        <div style={{ marginBottom: compact ? 12 : 18 }}>
          <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Profit routes {density === "operator" ? `(${routes.length})` : "(top 3)"}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {routes.map((route) => (
              <div
                key={route.id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 12,
                  padding: "8px 12px",
                  background: route.id === top.id ? "rgba(0, 240, 255, 0.06)" : "rgba(0,0,0,0.2)",
                  borderRadius: 8,
                  border: `1px solid ${route.id === top.id ? "rgba(0, 240, 255, 0.2)" : "rgba(255,255,255,0.06)"}`,
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{route.name}</div>
                  {density === "operator" && (
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                      {route.blocked_by.length > 0 ? `Blocked: ${route.blocked_by.join(", ")}` : route.status_note}
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                  {route.human_gated && (
                    <span className="mono" style={{ fontSize: 9, color: "var(--amber)", textTransform: "uppercase" }}>
                      human
                    </span>
                  )}
                  <span className="mono" style={{ fontWeight: 700, color: routeScoreColor(route.priority_score) }}>
                    {route.priority_score.toFixed(1)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {density !== "guided" && (
        <div>
          <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Backlog ({actionable.length} actionable)
          </div>
          <ul style={{ padding: 0, margin: 0 }}>
            {actionable.map((item) => (
              <BacklogRow key={item.charter} item={item} compact={compact} />
            ))}
          </ul>

          {humanGated.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <button
                type="button"
                onClick={() => setHumanGatedOpen((v) => !v)}
                aria-expanded={humanGatedOpen}
                style={{
                  width: "100%",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "10px 12px",
                  background: "rgba(245, 158, 11, 0.08)",
                  border: "1px solid rgba(245, 158, 11, 0.25)",
                  borderRadius: 8,
                  color: "var(--amber)",
                  cursor: "pointer",
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                <span>Human-gated items ({humanGated.length})</span>
                <span className="mono">{humanGatedOpen ? "▾" : "▸"}</span>
              </button>
              {humanGatedOpen && (
                <ul style={{ padding: 0, margin: "8px 0 0" }}>
                  {humanGated.map((item) => (
                    <BacklogRow key={item.charter} item={item} compact={compact} />
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {density === "operator" && assessment.immediate_technical_actions.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Immediate technical actions
          </div>
          <ul style={{ padding: 0, margin: 0 }}>
            {assessment.immediate_technical_actions.map((action) => (
              <li
                key={action.charter}
                style={{
                  marginBottom: 8,
                  padding: "8px 12px",
                  background: "rgba(0, 82, 255, 0.08)",
                  borderRadius: 8,
                  border: "1px solid rgba(0, 82, 255, 0.2)",
                  listStyle: "none",
                  fontSize: 12,
                }}
              >
                <strong>{action.title}</strong>
                <div style={{ color: "var(--text-muted)", marginTop: 4 }}>{action.detail}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
