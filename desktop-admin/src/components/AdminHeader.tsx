import type { CSSProperties } from "react";
import type { ServerStatus } from "@dashboard/hooks/useSSE";

type AdminHeaderProps = {
  apiBase: string;
  serverStatus: ServerStatus;
  doctorReady: boolean;
  onOpenSettings: () => void;
  onReconnect: () => void;
  onRefresh: () => void;
};

const STATUS_COLOR: Record<ServerStatus, string> = {
  connected: "var(--green)",
  degraded: "var(--amber)",
  disconnected: "var(--red)",
  checking: "var(--text-muted)",
};

export function AdminHeader({
  apiBase,
  serverStatus,
  doctorReady,
  onOpenSettings,
  onReconnect,
  onRefresh,
}: AdminHeaderProps) {
  const isElectron = Boolean(window.x402Desktop?.isElectron);

  return (
    <header
      className="mc-operator-header"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        padding: "12px 16px",
        borderBottom: "1px solid var(--border)",
        background: "rgba(0,0,0,0.35)",
        flexWrap: "wrap",
      }}
    >
      <div>
        <div style={{ fontSize: 18, fontWeight: 700 }}>
          <span style={{ color: "var(--neon-cyan)" }}>x402</span> // admin
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Operator desktop · density locked · {isElectron ? "Electron" : "web shell"}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span
          className="mono"
          style={{
            fontSize: 11,
            padding: "4px 8px",
            borderRadius: 6,
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.1)",
            maxWidth: 280,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={apiBase}
        >
          {apiBase}
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: STATUS_COLOR[serverStatus],
            }}
          />
          SSE {serverStatus}
        </span>
        <span style={{ fontSize: 12, color: doctorReady ? "var(--green)" : "var(--amber)" }}>
          {doctorReady ? "doctor ok" : "doctor warn"}
        </span>
        <button type="button" onClick={onRefresh} style={btnStyle()}>Refresh</button>
        <button type="button" onClick={onReconnect} style={btnStyle()}>Reconnect SSE</button>
        <button type="button" onClick={onOpenSettings} style={btnStyle(true)}>API settings</button>
      </div>
    </header>
  );
}

function btnStyle(primary = false): CSSProperties {
  return {
    background: primary ? "linear-gradient(135deg, var(--neon-cyan), var(--base))" : "rgba(255,255,255,0.06)",
    border: primary ? "none" : "1px solid rgba(255,255,255,0.12)",
    color: primary ? "#000" : "#fff",
    fontWeight: primary ? 700 : 400,
    padding: "6px 12px",
    borderRadius: 6,
    fontSize: 12,
    cursor: "pointer",
  };
}
