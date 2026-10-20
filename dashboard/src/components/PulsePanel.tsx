import type { PulseResponse } from "../api/client";

const VERDICT_COLOR: Record<PulseResponse["assessment"]["verdict"], string> = {
  SETTLE_NOW: "var(--green)",
  SETTLE_SOON: "var(--amber)",
  HOLD_IF_FLEXIBLE: "var(--text-muted)",
};

const VERDICT_LABEL: Record<PulseResponse["assessment"]["verdict"], string> = {
  SETTLE_NOW: "SETTLE NOW",
  SETTLE_SOON: "SETTLE SOON",
  HOLD_IF_FLEXIBLE: "HOLD IF FLEXIBLE",
};

const TREND_ARROW: Record<PulseResponse["utilization"]["trend"], string> = {
  rising: "↑",
  falling: "↓",
  flat: "→",
};

const num: React.CSSProperties = { fontVariantNumeric: "tabular-nums" };

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ minWidth: 96 }}>
      <div style={{ fontSize: 11, textTransform: "uppercase", color: "var(--text-muted)" }}>
        {label}
      </div>
      <div className="mono" style={{ fontSize: 18, ...num }}>
        {children}
      </div>
    </div>
  );
}

export function PulsePanel({ pulse }: { pulse: PulseResponse | null }) {
  if (!pulse) {
    return (
      <section id="panel-pulse" className="panel" style={{ gridColumn: "span 12" }}>
        <h3 style={{ margin: 0 }}>Base Network Pulse</h3>
        <div style={{ color: "var(--text-muted)", fontSize: 14, marginTop: 8 }}>
          Fetching live Base conditions…
        </div>
      </section>
    );
  }

  const { fees, utilization, settlement_cost, assessment, network } = pulse;
  const verdictColor = VERDICT_COLOR[assessment.verdict];
  const pctSign = fees.next_base_fee_change_pct >= 0 ? "+" : "";

  return (
    <section id="panel-pulse" className="panel" style={{ gridColumn: "span 12" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Base Network Pulse</h3>
        <span
          className="mono"
          style={{
            display: "inline-block",
            padding: "4px 12px",
            borderRadius: 999,
            fontSize: 13,
            fontWeight: 700,
            color: "#000",
            background: verdictColor,
          }}
        >
          {VERDICT_LABEL[assessment.verdict]}
        </span>
      </div>

      <div
        style={{
          display: "flex",
          gap: 24,
          flexWrap: "wrap",
          margin: "16px 0",
          padding: "12px 0",
          borderTop: "1px solid var(--border)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <Stat label="Base fee">{fees.base_fee_gwei.toFixed(3)} gwei</Stat>
        <Stat label="Next base fee">
          <span style={{ color: fees.next_base_fee_change_pct >= 0 ? "var(--amber)" : "var(--green)" }}>
            {pctSign}
            {fees.next_base_fee_change_pct.toFixed(1)}%
          </span>
        </Stat>
        <Stat label="Utilization">
          {utilization.now_pct.toFixed(0)}%{" "}
          <span style={{ color: "var(--text-muted)" }}>{TREND_ARROW[utilization.trend]}</span>
        </Stat>
        <Stat label="x402 settle">${settlement_cost.x402_settle.usd.toFixed(4)}</Stat>
        <Stat label="Block / TPS">
          {network.block_time_s.toFixed(1)}s · {network.tps_est.toFixed(1)} tps
        </Stat>
      </div>

      <div style={{ fontSize: 14, color: "var(--text)" }}>{assessment.rationale}</div>
      <div className="mono" style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6 }}>
        Window: {assessment.window}
      </div>
    </section>
  );
}
