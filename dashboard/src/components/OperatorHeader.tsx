import { type ServerStatus } from "../hooks/useSSE";
import { formatUsdcAtomic } from "../utils/usdc";
import { relativeTime } from "../utils/time";

export function OperatorHeader({
  status,
  lastSync,
  netMarginAtomic,
  grossRevenueAtomic,
  spendAtomic,
  alerts,
  onRetry,
}: {
  status: ServerStatus;
  lastSync: string | null;
  netMarginAtomic: number;
  grossRevenueAtomic: number;
  spendAtomic: number;
  alerts: string[];
  onRetry: () => void;
}) {
  const statusColor = 
    status === "connected" ? "var(--green)" : 
    status === "degraded" ? "var(--amber)" : 
    status === "checking" ? "var(--blue)" : "var(--red)";

  const lastSyncLabel = lastSync ? relativeTime(lastSync) : "Never";

  return (
    <div
      className="mc-operator-header"
      style={{
        background: "var(--panel-2)",
        borderBottom: "1px solid var(--line)",
        padding: "10px 16px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        flexWrap: "wrap",
        fontSize: 13,
      }}
    >
      <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
        <strong style={{ fontFamily: "var(--font-heading)", fontSize: 16, letterSpacing: "-0.02em", color: "#fff", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ color: "var(--neon-cyan)" }}>x402</span> // operator
        </strong>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontWeight: 700, textTransform: "uppercase", color: statusColor }}>
            {status}
          </span>
          <span style={{ color: "var(--text-muted)", fontSize: 11 }} title={lastSync || "No sync yet"}>
            · {lastSyncLabel}
          </span>
        </div>

        <div style={{ display: "flex", gap: 12, color: "var(--text-muted)", borderLeft: "1px solid var(--border)", paddingLeft: 16 }}>
          <span>
            Rev: <strong style={{ color: "var(--green)" }}>{formatUsdcAtomic(grossRevenueAtomic)}</strong>
          </span>
          <span>
            Spend: <strong style={{ color: "var(--usdc)" }}>{formatUsdcAtomic(spendAtomic)}</strong>
          </span>
          <span>
            Net: <strong style={{ color: netMarginAtomic >= 0 ? "var(--green)" : "var(--amber)" }}>
              {formatUsdcAtomic(netMarginAtomic)}
            </strong>
          </span>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center", borderLeft: "1px solid var(--border)", paddingLeft: 16 }}>
          {alerts.length > 0 ? (
            <span style={{ color: "var(--amber)", fontWeight: 600 }}>
              ⚠ {alerts[0]} {alerts.length > 1 && `(+${alerts.length - 1})`}
            </span>
          ) : (
            <span style={{ color: "var(--dim)" }}>✓ No issues</span>
          )}
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        {status !== "connected" && (
          <button
            onClick={onRetry}
            style={{ background: "var(--amber)", border: "none", color: "#000", padding: "4px 8px", borderRadius: 4, cursor: "pointer", fontWeight: 600, fontSize: 11 }}
          >
            Retry connection
          </button>
        )}
      </div>
    </div>
  );
}
