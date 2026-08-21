import type { LedgerRow } from "../types/api";
import { baseScanUrl, formatUsdcHuman, networkLabel, relativeTime, truncateHash } from "../lib/format";

interface LedgerTableProps {
  title: string;
  rows: LedgerRow[];
  density: string;
  guidedHelp?: string;
  emptyMessage?: string;
  emptyAction?: string;
  onExport?: () => void;
}

export function LedgerTable({
  title,
  rows,
  density,
  guidedHelp,
  emptyMessage = "No entries yet",
  emptyAction,
  onExport,
}: LedgerTableProps) {
  return (
    <div className="panel" style={{ gridColumn: "span 6", minHeight: "180px", display: "flex", flexDirection: "column" }}>
      <div className="panel-title">
        {title}
        {density === "guided" && guidedHelp && (
          <span title={guidedHelp} style={{ cursor: "help", opacity: 0.6 }}>?</span>
        )}
        {onExport && rows.length > 0 && (
          <button
            onClick={onExport}
            style={{
              marginLeft: "auto",
              background: "none",
              border: "1px solid var(--color-border)",
              borderRadius: "4px",
              color: "var(--color-text-muted)",
              padding: "2px 6px",
              fontSize: "10px",
              cursor: "pointer",
            }}
            aria-label={`Export ${title} as CSV`}
          >
            CSV
          </button>
        )}
      </div>

      {rows.length === 0 ? (
        <div className="empty-state">
          <span>{emptyMessage}</span>
          {emptyAction && <span style={{ fontSize: "12px" }}>{emptyAction}</span>}
        </div>
      ) : (
        <div style={{ overflow: "auto", flex: 1, maxHeight: "300px" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "12px",
            }}
          >
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                <th style={thStyle}>Time</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Amount</th>
                <th style={thStyle}>Network</th>
                <th style={thStyle}>Tx</th>
                <th style={thStyle}>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const network = row.network || "eip155:84532";
                const isTestnet = network.includes("84532");
                return (
                  <tr key={`${row.ts}-${i}`} style={{ borderBottom: "1px solid var(--color-border)" }}>
                    <td style={tdStyle} title={row.ts}>
                      <span className="mono">{relativeTime(row.ts)}</span>
                    </td>
                    <td style={{ ...tdStyle, textAlign: "right" }}>
                      <span className="mono" style={{ color: "var(--color-usdc)" }}>
                        {formatUsdcHuman(row.amount_usdc ?? 0)}
                      </span>
                      {density === "operator" && row.amount_atomic != null && (
                        <span style={{ color: "var(--color-text-muted)", fontSize: "10px", marginLeft: "4px" }}>
                          ({row.amount_atomic})
                        </span>
                      )}
                    </td>
                    <td style={tdStyle}>
                      <span
                        className={`chip ${isTestnet ? "chip-testnet" : "chip-mainnet"}`}
                        style={{ fontSize: "10px" }}
                      >
                        {networkLabel(network)}
                      </span>
                    </td>
                    <td style={tdStyle}>
                      {row.tx_hash ? (
                        <a
                          href={baseScanUrl(row.tx_hash, network)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mono"
                          style={{ color: "var(--color-usdc)", textDecoration: "none", fontSize: "11px" }}
                          title={row.tx_hash}
                        >
                          {truncateHash(row.tx_hash)}
                        </a>
                      ) : (
                        <span style={{ color: "var(--color-text-muted)" }}>—</span>
                      )}
                    </td>
                    <td style={tdStyle}>
                      <StatusDot status={row.status} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatusDot({ status }: { status?: string }) {
  const s = (status || "").toLowerCase();
  let dotClass = "dot-amber";
  let label = "pending";
  if (s === "settled" || s === "confirmed") {
    dotClass = "dot-green";
    label = "settled";
  } else if (s === "failed") {
    dotClass = "dot-red";
    label = "failed";
  }
  return (
    <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
      <span className={`dot ${dotClass}`} aria-hidden="true" />
      <span style={{ fontSize: "11px", color: "var(--color-text-muted)" }}>{label}</span>
    </span>
  );
}

const thStyle: React.CSSProperties = {
  padding: "6px 8px",
  textAlign: "left",
  fontWeight: 500,
  color: "var(--color-text-muted)",
  fontSize: "11px",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  position: "sticky",
  top: 0,
  background: "var(--color-panel)",
};

const tdStyle: React.CSSProperties = {
  padding: "6px 8px",
  verticalAlign: "middle",
};
