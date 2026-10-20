import type { LedgerRow } from "../types/api";
import { formatUsdcHuman } from "../lib/format";

interface NetPositionProps {
  spend: LedgerRow[];
  revenue: LedgerRow[];
  defaultPrice: string;
  density: string;
}

export function NetPosition({ spend, revenue, defaultPrice, density }: NetPositionProps) {
  const totalSpend = spend.reduce((s, r) => s + (r.amount_usdc ?? 0), 0);
  const totalRevenue = revenue.reduce((s, r) => s + (r.amount_usdc ?? 0), 0);
  const net = totalRevenue - totalSpend;
  const isPositive = net >= 0;

  // Break-even progress bar when negative
  const progressPct =
    !isPositive && totalRevenue > 0
      ? Math.min((totalRevenue / totalSpend) * 100, 100)
      : isPositive
        ? 100
        : 0;

  // Calls to break even
  const priceNum = parseFloat(defaultPrice.replace(/[^0-9.]/g, "")) || 0.01;
  const callsToBreakEven =
    !isPositive && priceNum > 0 ? Math.ceil(Math.abs(net) / priceNum) : 0;

  return (
    <div className="panel" style={{ gridColumn: "span 4" }}>
      <div className="panel-title">
        Net Position
        {density === "guided" && (
          <span
            title="Revenue minus spend. Green means self-sustaining."
            style={{ cursor: "help", opacity: 0.6 }}
          >
            ?
          </span>
        )}
      </div>
      <div
        className="mono"
        style={{
          fontSize: "32px",
          fontWeight: 600,
          color: isPositive ? "var(--color-green)" : "var(--color-red)",
          lineHeight: 1.2,
        }}
      >
        {net >= 0 ? "+" : ""}
        {formatUsdcHuman(net)}
      </div>
      <div
        style={{
          fontSize: "12px",
          color: "var(--color-text-muted)",
          marginTop: "4px",
        }}
      >
        {isPositive
          ? "Self-sustaining"
          : `${callsToBreakEven} calls to break even at ${defaultPrice}/call`}
      </div>

      {/* Progress bar */}
      <div
        style={{
          marginTop: "12px",
          height: "4px",
          background: "var(--color-border)",
          borderRadius: "2px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${progressPct}%`,
            background: isPositive ? "var(--color-green)" : "var(--color-amber)",
            borderRadius: "2px",
            transition: "width 150ms ease-out",
          }}
        />
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: "11px",
          color: "var(--color-text-muted)",
          marginTop: "4px",
        }}
      >
        <span>Spent: {formatUsdcHuman(totalSpend)}</span>
        <span>Revenue: {formatUsdcHuman(totalRevenue)}</span>
      </div>
    </div>
  );
}
