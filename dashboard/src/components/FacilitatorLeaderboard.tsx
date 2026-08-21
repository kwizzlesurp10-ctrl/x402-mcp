

interface FacilitatorNode {
  id: string;
  name: string;
  url: string;
  uptime: string;
  avgLatencyMs: number;
  feeRate: string;
  supportedSchemes: string[];
  chains: string[];
  status: "active" | "degraded" | "syncing";
}

const FACILITATORS: FacilitatorNode[] = [
  {
    id: "fac-01",
    name: "x402 Foundation Facilitator",
    url: "https://x402.org/facilitator",
    uptime: "99.99%",
    avgLatencyMs: 140,
    feeRate: "0.00%",
    supportedSchemes: ["exact", "upto", "batch-settlement"],
    chains: ["Base", "Solana", "Ethereum", "Arbitrum"],
    status: "active",
  },
  {
    id: "fac-02",
    name: "Coinbase CDP Facilitator",
    url: "https://api.cdp.coinbase.com/x402",
    uptime: "99.98%",
    avgLatencyMs: 95,
    feeRate: "0.00%",
    supportedSchemes: ["exact", "bazaar-discovery"],
    chains: ["Base"],
    status: "active",
  },
  {
    id: "fac-03",
    name: "Pay.sh Facilitator Gateway",
    url: "https://pay.sh/v1/x402",
    uptime: "99.95%",
    avgLatencyMs: 180,
    feeRate: "0.10%",
    supportedSchemes: ["exact", "upto"],
    chains: ["Base", "Solana"],
    status: "active",
  },
  {
    id: "fac-04",
    name: "Agentic.Market Settlement Engine",
    url: "https://agentic.market/facilitator",
    uptime: "99.90%",
    avgLatencyMs: 210,
    feeRate: "0.05%",
    supportedSchemes: ["exact", "batch-settlement"],
    chains: ["Base", "Arbitrum"],
    status: "active",
  },
];

export function FacilitatorLeaderboard({ density }: { density: string }) {
  return (
    <div
      style={{
        gridColumn: density === "compact" ? "span 12" : "span 6",
        borderRadius: "12px",
        background: "rgba(13, 17, 29, 0.75)",
        backdropFilter: "blur(16px)",
        border: "1px solid rgba(0, 240, 255, 0.15)",
        padding: "16px 20px",
        display: "flex",
        flexDirection: "column",
        gap: "14px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontSize: "15px", fontWeight: 600, color: "#F3F4F6" }}>
            Facilitator Network Leaderboard
          </div>
          <div style={{ fontSize: "12px", color: "#9CA3AF" }}>
            Verified payment facilitators for EVM & Solana settlements
          </div>
        </div>
        <span
          style={{
            fontSize: "11px",
            fontFamily: "var(--font-mono, monospace)",
            padding: "4px 8px",
            borderRadius: "6px",
            background: "rgba(0, 240, 255, 0.1)",
            border: "1px solid rgba(0, 240, 255, 0.25)",
            color: "#00F0FF",
          }}
        >
          18 Active Facilitators
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {FACILITATORS.map((fac) => (
          <div
            key={fac.id}
            style={{
              padding: "12px 14px",
              borderRadius: "8px",
              background: "rgba(255, 255, 255, 0.02)",
              border: "1px solid rgba(255, 255, 255, 0.06)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "12px",
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span className="dot dot-green" aria-hidden="true" />
                <span style={{ fontSize: "13px", fontWeight: 600, color: "#F3F4F6" }}>
                  {fac.name}
                </span>
              </div>
              <span
                style={{
                  fontSize: "11px",
                  color: "#6B7280",
                  fontFamily: "var(--font-mono, monospace)",
                }}
              >
                {fac.url}
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
              <div style={{ textAlign: "right" }}>
                <div
                  style={{
                    fontSize: "12px",
                    fontWeight: 600,
                    color: "#10B981",
                    fontFamily: "var(--font-mono, monospace)",
                  }}
                >
                  ⚡ {fac.avgLatencyMs}ms
                </div>
                <div style={{ fontSize: "10px", color: "#9CA3AF" }}>{fac.uptime} Uptime</div>
              </div>

              <div style={{ display: "flex", gap: "4px", flexWrap: "wrap", maxWidth: "140px" }}>
                {fac.supportedSchemes.map((scheme) => (
                  <span
                    key={scheme}
                    style={{
                      fontSize: "9px",
                      fontFamily: "var(--font-mono, monospace)",
                      padding: "2px 6px",
                      borderRadius: "4px",
                      background: "rgba(139, 92, 246, 0.15)",
                      color: "#C4B5FD",
                    }}
                  >
                    {scheme}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
