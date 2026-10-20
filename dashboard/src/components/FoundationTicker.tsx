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
          x402 protocol
        </span>
      </div>
      <p
        style={{
          margin: 0,
          fontSize: "12px",
          color: "#9CA3AF",
          lineHeight: 1.45,
        }}
      >
        Linux Foundation at the protocol layer. This node is independent and is not certified
        by the Linux Foundation or any payment network.
      </p>
    </div>
  );
}
