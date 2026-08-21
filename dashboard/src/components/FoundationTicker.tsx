

const MEMBERS = [
  { name: "Coinbase", role: "Premier Founder", badge: "Base Facilitator" },
  { name: "Cloudflare", role: "Infrastructure", badge: "Edge Gateways" },
  { name: "AWS", role: "Cloud Partner", badge: "Resource Host" },
  { name: "Circle", role: "USDC Issuer", badge: "Settlement Asset" },
  { name: "Visa", role: "Payment Network", badge: "Facilitator Rail" },
  { name: "Mastercard", role: "Payment Network", badge: "Facilitator Rail" },
  { name: "Stripe", role: "Merchant Engine", badge: "Checkout Bridge" },
  { name: "Google", role: "Cloud & AI", badge: "Resource Provider" },
  { name: "Adyen", role: "Global Payments", badge: "Enterprise Rail" },
  { name: "AMEX", role: "Financial Services", badge: "Enterprise Partner" },
  { name: "Solana Foundation", role: "Chain Partner", badge: "Solana Micropayments" },
];

export function FoundationTicker() {
  return (
    <div
      style={{
        borderRadius: "12px",
        background: "rgba(13, 17, 29, 0.75)",
        backdropFilter: "blur(16px)",
        border: "1px solid rgba(0, 240, 255, 0.12)",
        padding: "14px 20px",
        marginBottom: "16px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "16px",
        overflow: "hidden",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "10px", flexShrink: 0 }}>
        <div
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: "#00F0FF",
            boxShadow: "0 0 10px #00F0FF",
          }}
        />
        <span
          style={{
            fontSize: "11px",
            fontFamily: "var(--font-mono, monospace)",
            color: "#00F0FF",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            fontWeight: 600,
          }}
        >
          Linux Foundation x402 Ecosystem
        </span>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "20px",
          overflowX: "auto",
          scrollbarWidth: "none",
          msOverflowStyle: "none",
        }}
      >
        {MEMBERS.map((m) => (
          <div
            key={m.name}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              flexShrink: 0,
              padding: "4px 10px",
              borderRadius: "6px",
              background: "rgba(255, 255, 255, 0.03)",
              border: "1px solid rgba(255, 255, 255, 0.06)",
            }}
          >
            <span style={{ fontSize: "13px", fontWeight: 600, color: "#E5E7EB" }}>{m.name}</span>
            <span
              style={{
                fontSize: "10px",
                fontFamily: "var(--font-mono, monospace)",
                padding: "2px 6px",
                borderRadius: "4px",
                background: "rgba(59, 130, 246, 0.15)",
                color: "#60A5FA",
              }}
            >
              {m.badge}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
