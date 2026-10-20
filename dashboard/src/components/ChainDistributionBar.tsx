

interface ChainData {
  id: string;
  name: string;
  share: number; // percentage
  color: string;
  asset: string;
  avgLatency: string;
}

const CHAINS: ChainData[] = [
  { id: "eip155:8453", name: "Base Mainnet", share: 68, color: "#0052FF", asset: "USDC", avgLatency: "1.2s" },
  { id: "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp", name: "Solana Mainnet", share: 22, color: "#14F195", asset: "USDC", avgLatency: "0.4s" },
  { id: "eip155:1", name: "Ethereum Mainnet", share: 6, color: "#627EEA", asset: "USDC", avgLatency: "12s" },
  { id: "eip155:42161", name: "Arbitrum One", share: 4, color: "#28A0F0", asset: "USDC", avgLatency: "0.8s" },
];

export function ChainDistributionBar({ density }: { density: string }) {
  return (
    <div
      style={{
        gridColumn: density === "compact" ? "span 6" : "span 12",
        borderRadius: "12px",
        background: "rgba(13, 17, 29, 0.75)",
        backdropFilter: "blur(16px)",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        padding: "16px 20px",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "14px", fontWeight: 600, color: "#F3F4F6" }}>
            Chain & Facilitator Settlement Share
          </span>
          <span
            style={{
              fontSize: "11px",
              fontFamily: "var(--font-mono, monospace)",
              padding: "2px 8px",
              borderRadius: "4px",
              background: "rgba(16, 185, 129, 0.15)",
              color: "#10B981",
            }}
          >
            Live Settlement Pulse
          </span>
        </div>
        <span style={{ fontSize: "12px", color: "#9CA3AF" }}>
          Primary Asset: <strong style={{ color: "#2775CA" }}>USDC</strong>
        </span>
      </div>

      {/* Multi-segment Progress Bar */}
      <div
        style={{
          display: "flex",
          height: "10px",
          width: "100%",
          borderRadius: "5px",
          overflow: "hidden",
          background: "#1F2937",
        }}
      >
        {CHAINS.map((chain) => (
          <div
            key={chain.id}
            style={{
              width: `${chain.share}%`,
              background: chain.color,
              transition: "width 0.4s ease-out",
              boxShadow: `0 0 10px ${chain.color}66`,
            }}
            title={`${chain.name}: ${chain.share}% (${chain.avgLatency} avg)`}
          />
        ))}
      </div>

      {/* Chain Metric Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${CHAINS.length}, 1fr)`,
          gap: "12px",
          marginTop: "4px",
        }}
      >
        {CHAINS.map((chain) => (
          <div
            key={chain.id}
            style={{
              padding: "10px 12px",
              borderRadius: "8px",
              background: "rgba(255, 255, 255, 0.02)",
              border: `1px solid ${chain.color}33`,
              display: "flex",
              flexDirection: "column",
              gap: "4px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <div
                style={{
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: chain.color,
                }}
              />
              <span style={{ fontSize: "12px", fontWeight: 600, color: "#E5E7EB" }}>
                {chain.name}
              </span>
            </div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                marginTop: "2px",
              }}
            >
              <span
                style={{
                  fontSize: "18px",
                  fontWeight: 700,
                  fontFamily: "var(--font-mono, monospace)",
                  color: "#F9FAFB",
                }}
              >
                {chain.share}%
              </span>
              <span
                style={{
                  fontSize: "11px",
                  color: "#9CA3AF",
                  fontFamily: "var(--font-mono, monospace)",
                }}
              >
                ⚡ {chain.avgLatency}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
