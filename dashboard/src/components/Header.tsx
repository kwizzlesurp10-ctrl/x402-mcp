import type { ConnectionStatus, DensityMode } from "../types/api";
import { networkLabel } from "../lib/format";

interface HeaderProps {
  network: string;
  tier: string;
  status: ConnectionStatus;
  demo: boolean;
  onToggleDemo: () => void;
  density: DensityMode;
  onDensityChange: (mode: DensityMode) => void;
  onOpenWizard: () => void;
}

const statusLabels: Record<ConnectionStatus, string> = {
  connected: "Live",
  polling: "Polling",
  disconnected: "Offline",
};

const statusColors: Record<ConnectionStatus, string> = {
  connected: "dot-green",
  polling: "dot-amber",
  disconnected: "dot-red",
};

export function Header({
  network,
  tier,
  status,
  demo,
  onToggleDemo,
  density,
  onDensityChange,
  onOpenWizard,
}: HeaderProps) {
  const isTestnet = network.includes("84532") || network.toLowerCase().includes("sepolia");

  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "12px 24px",
        borderBottom: "1px solid var(--color-border)",
        background: "var(--color-panel)",
        flexWrap: "wrap",
        gap: "8px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontWeight: 600,
            fontSize: "15px",
            letterSpacing: "0.02em",
            whiteSpace: "nowrap"
          }}
        >
          x402 <span style={{ color: "var(--color-text-muted)" }}>//</span>{" "}
          dashboard
        </span>

        <span className={`chip ${isTestnet ? "chip-testnet" : "chip-mainnet"}`}>
          {networkLabel(network)}
        </span>

        {tier !== "free" && (
          <span
            className="chip"
            style={{
              background: "rgba(47, 191, 113, 0.15)",
              color: "var(--color-green)",
            }}
          >
            PRO
          </span>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <button
          onClick={onOpenWizard}
          style={{
            background: "none",
            border: "1px solid var(--color-border)",
            borderRadius: "6px",
            color: "var(--color-text-muted)",
            padding: "4px 10px",
            fontSize: "12px",
            cursor: "pointer",
          }}
          aria-label="Open setup wizard"
        >
          Setup
        </button>

        <select
          value={density}
          onChange={(e) => onDensityChange(e.target.value as DensityMode)}
          aria-label="Density mode"
          style={{
            background: "var(--color-base)",
            border: "1px solid var(--color-border)",
            borderRadius: "6px",
            color: "var(--color-text-muted)",
            padding: "4px 8px",
            fontSize: "12px",
            cursor: "pointer",
          }}
        >
          <option value="guided">Guided</option>
          <option value="standard">Standard</option>
          <option value="operator">Operator</option>
        </select>

        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "12px",
            color: demo ? "var(--color-amber)" : "var(--color-text-muted)",
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={demo}
            onChange={onToggleDemo}
            style={{ cursor: "pointer" }}
            aria-label="Toggle demo mode"
          />
          Demo
        </label>

        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span
            className={`dot ${statusColors[status]} ${status === "connected" ? "dot-live" : ""}`}
            style={{ color: status === "connected" ? "var(--color-green)" : undefined }}
            aria-hidden="true"
          />
          <span
            style={{
              fontSize: "11px",
              color: "var(--color-text-muted)",
              fontFamily: "var(--font-mono)",
            }}
            role="status"
          >
            {statusLabels[status]}
          </span>
        </div>
      </div>
    </header>
  );
}
