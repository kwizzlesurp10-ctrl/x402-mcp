import type { MissionStep } from "../utils/mission";

export function MissionProgress({
  steps,
  open,
  onToggle,
}: {
  steps: MissionStep[];
  open: boolean;
  onToggle: () => void;
}) {
  const done = steps.filter((s) => s.done).length;
  const pct = Math.round((done / (steps.length || 1)) * 100);

  return (
    <div className="panel mc-mission" style={{ margin: "0 16px 16px", padding: "14px 20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={onToggle}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--text)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: 0,
            fontFamily: "var(--font-heading)",
            fontSize: 15,
            fontWeight: 600,
          }}
        >
          <span style={{ color: "var(--neon-cyan)", fontSize: 16 }}>{open ? "▾" : "▸"}</span>
          <span>Mission Progress</span>
          <span className="mono" style={{ fontSize: 13, color: "var(--text-muted)", background: "rgba(255,255,255,0.06)", padding: "2px 8px", borderRadius: 10 }}>
            {done}/{steps.length} ({pct}%)
          </span>
        </button>
        <div className="mc-mission-bar" style={{ width: 140, height: 6, background: "rgba(255,255,255,0.08)", borderRadius: 3, overflow: "hidden" }}>
          <div
            style={{
              width: `${pct}%`,
              height: "100%",
              background: "linear-gradient(90deg, var(--neon-cyan), var(--green))",
              transition: "width 0.4s ease",
            }}
          />
        </div>
      </div>
      {open && (
        <ol style={{ margin: "14px 0 0", paddingLeft: 0, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 220px), 1fr))", gap: "8px 16px" }}>
          {steps.map((s) => (
            <li
              key={s.id}
              style={{
                color: s.done ? "var(--green)" : "var(--text-muted)",
                fontSize: 13,
                fontWeight: s.done ? 600 : 400,
                listStyleType: "none",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 18,
                  height: 18,
                  borderRadius: "50%",
                  fontSize: 11,
                  flexShrink: 0,
                  background: s.done ? "rgba(16, 185, 129, 0.15)" : "rgba(255,255,255,0.05)",
                  color: s.done ? "var(--green)" : "var(--text-muted)",
                  border: `1px solid ${s.done ? "var(--green)" : "rgba(255,255,255,0.1)"}`,
                }}
              >
                {s.done ? "✓" : "○"}
              </span>
              <span>{s.label}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}