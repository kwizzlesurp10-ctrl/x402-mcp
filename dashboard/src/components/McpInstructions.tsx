import { useState } from "react";

interface McpToolInfo {
  name: string;
  category: "Compliance & Diligence" | "Core Discovery & Settlement" | "Commerce & Quota" | "Swarm Agency" | "Infrastructure & Pulse" | "A2A Protocol";
  price: string;
  network?: string;
  description: string;
  highlight?: boolean;
}

const MCP_TOOLS: McpToolInfo[] = [
  // MARC-HD Diligence & Compliance
  {
    name: "mn_property_diligence",
    category: "Compliance & Diligence",
    price: "$0.85 USDC",
    network: "Base eip155:8453",
    description:
      "Minneapolis Autonomous Rental Compliance & Habitability Diligence (MARC-HD). Queries ArcGIS REST FeatureServers, normalizes addresses/PINs, computes composite 0-100 habitability score, tier penalties (T1-T3), and deterministic 4-class compliance verdict.",
    highlight: true,
  },
  {
    name: "city.list",
    category: "Compliance & Diligence",
    price: "Free",
    network: "Base eip155:8453",
    description:
      "List US City Open-Data Compliance Network cities with paid_url, sample_url, and price terms across 14 jurisdictions.",
  },
  {
    name: "city.sample",
    category: "Compliance & Diligence",
    price: "Free",
    network: "Base eip155:8453",
    description:
      "Free fixed-address property compliance sample for any supported city code (e.g. city_code='chi') to verify data schema.",
  },
  {
    name: "city.check",
    category: "Compliance & Diligence",
    price: "$0.01 USDC",
    network: "Base eip155:8453",
    description:
      "Paid US city property compliance check via x402 on the same HTTP resource buyers use. Settles USDC on Base/Solana/Arbitrum.",
  },

  // Core x402 Discovery & Settlement
  {
    name: "x402.agent_card",
    category: "Core Discovery & Settlement",
    price: "Free",
    description:
      "Return the A2A Protocol v1.0 Agent ID Card and MCP server card. Optional target_id filters to skill ID, name, or tag.",
  },
  {
    name: "x402.discover",
    category: "Core Discovery & Settlement",
    price: "Free",
    description:
      "Discover paid HTTP APIs in the x402 Bazaar via facilitator catalogs before probing or paying.",
  },
  {
    name: "x402.probe",
    category: "Core Discovery & Settlement",
    price: "Free",
    description:
      "Probe a URL for HTTP 402 PAYMENT-REQUIRED terms using x402 client SDK without spending gas or funds.",
  },
  {
    name: "x402.pay_and_fetch",
    category: "Core Discovery & Settlement",
    price: "Upstream price",
    description:
      "Pay USDC via x402 and fetch a protected HTTP resource in one atomic call (requires EVM_PRIVATE_KEY on host).",
  },
  {
    name: "x402.build_seller",
    category: "Core Discovery & Settlement",
    price: "Free",
    description:
      "Build seller-side x402 payment requirements and discovery fields to catalog your own HTTP resource in Bazaar.",
  },
  {
    name: "x402.verify",
    category: "Core Discovery & Settlement",
    price: "Free",
    description:
      "Verify an x402 PAYMENT-SIGNATURE against PAYMENT-REQUIRED terms via facilitator before releasing paid content.",
  },
  {
    name: "x402.networks",
    category: "Core Discovery & Settlement",
    price: "Free",
    description:
      "List supported settlement networks, CAIP-2 IDs, facilitators, and x402 v2 protocol header names.",
  },

  // Commerce & Quota
  {
    name: "commerce.pro_requirements",
    category: "Commerce & Quota",
    price: "Free",
    description:
      "Build x402 payment requirements to purchase the Pro quota tier. Pay terms then call commerce.activate_pro.",
  },
  {
    name: "commerce.activate_pro",
    category: "Commerce & Quota",
    price: "$29.00 USDC",
    network: "Base eip155:8453",
    description:
      "Verify Pro-tier x402 payment and unlock 50,000 monthly quota calls and elevated rate limits for the agent.",
  },
  {
    name: "commerce.credits_requirements",
    category: "Commerce & Quota",
    price: "Free",
    description:
      "Build x402 payment requirements to buy a pack of per-use MCP tool credits.",
  },
  {
    name: "commerce.purchase_credits",
    category: "Commerce & Quota",
    price: "Pack rate",
    network: "Base eip155:8453",
    description:
      "Verify an x402 payment and add per-use tool credits to the agent quota balance.",
  },

  // Swarm Agency
  {
    name: "swarm.research",
    category: "Swarm Agency",
    price: "Free / inputs",
    description:
      "Run the autonomous swarm agency: compose a research composite product from free/paid inputs and list for resale.",
  },
  {
    name: "swarm.settle",
    category: "Swarm Agency",
    price: "Product price",
    description:
      "Verify and settle buyer x402 payment for a listed swarm composite product and record revenue in the ledger.",
  },
  {
    name: "swarm.revenue",
    category: "Swarm Agency",
    price: "Free",
    description:
      "Get swarm composite economics: spend, composite sales, realized margin, LTV:CAC, and per-source performance scores.",
  },

  // Infrastructure & Pulse
  {
    name: "pulse.base",
    category: "Infrastructure & Pulse",
    price: "Free",
    description:
      "Get live Base Network Pulse: base fee, EIP-1559 projection, utilization, USD settlement cost, and settle-now verdict.",
  },
  {
    name: "ops.metrics",
    category: "Infrastructure & Pulse",
    price: "Free",
    description:
      "Get host OS telemetry: CPU, memory, swap, disk, network, and an ok/warn/critical health verdict.",
  },

  // A2A Protocol
  {
    name: "a2a.resolve_card",
    category: "A2A Protocol",
    price: "Free",
    description:
      "Discover and inspect an external A2A node by domain/URL with AP2 payment extension validation and SSRF protection.",
  },
];

export function McpInstructions() {
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [expanded, setExpanded] = useState<boolean>(true);

  const categories = [
    "ALL",
    "Compliance & Diligence",
    "Core Discovery & Settlement",
    "Commerce & Quota",
    "Swarm Agency",
    "Infrastructure & Pulse",
    "A2A Protocol",
  ];

  const displayedTools =
    selectedCategory === "ALL"
      ? MCP_TOOLS
      : MCP_TOOLS.filter((t) => t.category === selectedCategory);

  return (
    <section
      id="panel-mcp-instructions"
      className="panel"
      style={{
        gridColumn: "span 12",
        background: "linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(6, 12, 24, 0.95) 100%)",
        border: "1px solid rgba(0, 240, 255, 0.3)",
        boxShadow: "0 10px 40px rgba(0, 240, 255, 0.12)",
        position: "relative",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="pulsing-dot" style={{ width: 10, height: 10, background: "var(--neon-cyan)" }} />
            <h3 style={{ margin: 0, fontSize: 20, color: "#fff", fontFamily: "var(--font-heading)" }}>
              Model Context Protocol (MCP) — 21 Production Tools Active
            </h3>
            <span
              className="mono"
              style={{
                fontSize: 10,
                fontWeight: 700,
                padding: "2px 8px",
                borderRadius: 4,
                background: "rgba(0, 240, 255, 0.12)",
                border: "1px solid rgba(0, 240, 255, 0.3)",
                color: "var(--neon-cyan)",
              }}
            >
              Base eip155:8453
            </span>
          </div>
          <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 13 }}>
            FastMCP & A2A production tool catalog discoverable at <code style={{ color: "var(--neon-cyan)" }}>/.well-known/mcp</code> and <code style={{ color: "var(--neon-cyan)" }}>/.well-known/x402</code>.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          style={{
            background: "rgba(255, 255, 255, 0.05)",
            border: "1px solid rgba(255, 255, 255, 0.15)",
            color: "var(--neon-cyan)",
            borderRadius: 6,
            padding: "6px 12px",
            fontSize: 11,
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          {expanded ? "Collapse Details ▲" : "Expand All (21 Tools) ▼"}
        </button>
      </div>

      {/* Protocol Execution Flow Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div style={{ background: "rgba(0, 0, 0, 0.3)", padding: 12, borderRadius: 8, border: "1px solid rgba(255, 255, 255, 0.08)" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--neon-cyan)", textTransform: "uppercase" }}>
            1. Discover & Inspect
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
            Call <code>x402.discover</code> or <code>city.list</code> to discover paid endpoints, or <code>a2a.resolve_card</code> for external counterpart agent cards.
          </div>
        </div>

        <div style={{ background: "rgba(0, 0, 0, 0.3)", padding: 12, borderRadius: 8, border: "1px solid rgba(255, 255, 255, 0.08)" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--green)", textTransform: "uppercase" }}>
            2. Dry Run & Probe
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
            Execute <code>city.sample</code> or <code>x402.probe</code> to inspect payload shape, pricing, and network parameters without spending funds.
          </div>
        </div>

        <div style={{ background: "rgba(0, 0, 0, 0.3)", padding: 12, borderRadius: 8, border: "1px solid rgba(255, 255, 255, 0.08)" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--amber)", textTransform: "uppercase" }}>
            3. Challenge & Sign
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
            Unpaid calls return HTTP 402 challenge terms in <code>_meta["x402/payment-required"]</code>. Sign with agent wallet on Base mainnet.
          </div>
        </div>

        <div style={{ background: "rgba(0, 0, 0, 0.3)", padding: 12, borderRadius: 8, border: "1px solid rgba(255, 255, 255, 0.08)" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a855f7", textTransform: "uppercase" }}>
            4. Settle & Fulfill
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
            Inject payment signature into <code>_meta["x402/payment"]</code> or <code>PAYMENT-SIGNATURE</code> HTTP header to settle and receive authoritative output.
          </div>
        </div>
      </div>

      {expanded && (
        <>
          {/* Category Filter Tabs */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            {categories.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setSelectedCategory(cat)}
                style={{
                  background: selectedCategory === cat ? "var(--neon-cyan)" : "rgba(255, 255, 255, 0.05)",
                  color: selectedCategory === cat ? "#000" : "var(--text-muted)",
                  border: `1px solid ${selectedCategory === cat ? "var(--neon-cyan)" : "rgba(255, 255, 255, 0.1)"}`,
                  borderRadius: 6,
                  padding: "4px 10px",
                  fontSize: 11,
                  fontWeight: selectedCategory === cat ? 700 : 500,
                  cursor: "pointer",
                  transition: "all 0.2s ease",
                }}
              >
                {cat} {cat === "ALL" ? `(${MCP_TOOLS.length})` : ""}
              </button>
            ))}
          </div>

          {/* Tools Grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: 10,
              maxHeight: 420,
              overflowY: "auto",
              paddingRight: 4,
            }}
          >
            {displayedTools.map((tool) => (
              <div
                key={tool.name}
                style={{
                  background: tool.highlight
                    ? "linear-gradient(135deg, rgba(0, 240, 255, 0.1) 0%, rgba(16, 185, 129, 0.08) 100%)"
                    : "rgba(15, 23, 36, 0.6)",
                  border: tool.highlight
                    ? "1px solid rgba(0, 240, 255, 0.4)"
                    : "1px solid rgba(255, 255, 255, 0.07)",
                  borderRadius: 8,
                  padding: 10,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  gap: 6,
                }}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                    <code
                      className="mono"
                      style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: tool.highlight ? "var(--neon-cyan)" : "#fff",
                      }}
                    >
                      {tool.name}
                    </code>
                    <span
                      className="mono"
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        color: tool.price === "Free" ? "var(--text-muted)" : "var(--green)",
                        background: tool.price === "Free" ? "rgba(255, 255, 255, 0.05)" : "rgba(16, 185, 129, 0.12)",
                        padding: "2px 6px",
                        borderRadius: 4,
                        border: `1px solid ${tool.price === "Free" ? "rgba(255, 255, 255, 0.1)" : "rgba(16, 185, 129, 0.25)"}`,
                      }}
                    >
                      {tool.price}
                    </span>
                  </div>

                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.4 }}>
                    {tool.description}
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 10, color: "var(--text-muted)", paddingTop: 4, borderTop: "1px solid rgba(255, 255, 255, 0.05)" }}>
                  <span>{tool.category}</span>
                  {tool.network && <span className="mono" style={{ color: "var(--neon-cyan)" }}>{tool.network}</span>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
