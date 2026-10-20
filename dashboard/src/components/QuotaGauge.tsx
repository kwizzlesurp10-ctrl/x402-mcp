import type { AgentStats } from "../types/api";

interface QuotaGaugeProps {
  agents: AgentStats[];
  quota: number;
  density: string;
}

export function QuotaGauge({ agents, quota, density }: QuotaGaugeProps) {
  const totalCalls = agents.reduce((s, a) => s + a.calls_this_month, 0);
  const pct = quota > 0 ? Math.min((totalCalls / quota) * 100, 100) : 0;
  const isWarning = pct >= 80;

  // SVG radial gauge
  const size = 100;
  const stroke = 8;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const offset = circumference - (pct / 100) * circumference;

  return (
    <div className="panel" style={{ gridColumn: "span 4" }}>
      <div className="panel-title">
        Quota Burndown
        {density === "guided" && (
          <span
            title="Monthly MCP tool calls used vs. limit. Resets monthly."
            style={{ cursor: "help", opacity: 0.6 }}
          >
            ?
          </span>
        )}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "16px",
        }}
      >
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          aria-label={`Quota: ${totalCalls} of ${quota} used`}
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--color-border)"
            strokeWidth={stroke}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={isWarning ? "var(--color-amber)" : "var(--color-usdc)"}
            strokeWidth={stroke}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            style={{ transition: "stroke-dashoffset 150ms ease-out" }}
          />
          <text
            x={size / 2}
            y={size / 2}
            textAnchor="middle"
            dominantBaseline="central"
            fill="var(--color-text)"
            fontFamily="var(--font-mono)"
            fontSize="18"
            fontWeight="600"
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {Math.round(pct)}%
          </text>
        </svg>

        <div>
          <div className="mono" style={{ fontSize: "20px", fontWeight: 600 }}>
            {totalCalls.toLocaleString()}
          </div>
          <div style={{ fontSize: "12px", color: "var(--color-text-muted)" }}>
            of {quota.toLocaleString()} calls
          </div>
          {agents.length > 0 && (
            <div style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "4px" }}>
              {agents.length} agent{agents.length !== 1 ? "s" : ""}
            </div>
          )}
        </div>
      </div>

      {totalCalls === 0 && (
        <div className="empty-state" style={{ padding: "8px" }}>
          <span style={{ fontSize: "12px" }}>No calls yet — run your first free discovery</span>
        </div>
      )}
    </div>
  );
}
