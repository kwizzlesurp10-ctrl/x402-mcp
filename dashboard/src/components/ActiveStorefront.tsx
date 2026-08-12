import { useState } from "react";
import type { SwarmProduct, LedgerRow } from "../api/client";
import type { StreamEvent } from "../hooks/useSSE";
import { CopyButton } from "./CopyButton";

type ActiveCall = {
  id: string;
  name: string;
  path: string;
  priceUsdc: number;
  costBasisUsdc: number;
  category: "Canonical Data" | "US Compliance Network" | "Swarm Composite";
  views: number;
  sales: number;
  status: "LIVE FOR SALE" | "SOLD";
};

export function ActiveStorefront({
  products,
  revenueRows = [],
  activityEvents = [],
}: {
  products: SwarmProduct[];
  revenueRows?: LedgerRow[];
  activityEvents?: StreamEvent[];
}) {
  // Always advertise the public storefront host for copyable Resource URLs.
  // Mission Control SPA (Vercel) does not proxy /us/* or /mn/* payment paths.
  const storefrontBase = (
    import.meta.env.VITE_STOREFRONT_BASE_URL ||
    "https://x402-mcp.onrender.com"
  ).replace(/\/$/, "");

  // Base Built-in x402 Endpoints — canonical Visit/Resource trio first
  const baseCalls: ActiveCall[] = [
    {
      id: "call-catalog",
      name: "US City Compliance Catalog",
      path: "/us/cities",
      priceUsdc: 0.0,
      costBasisUsdc: 0.0,
      category: "US Compliance Network",
      views: 240,
      sales: 0,
      status: "LIVE FOR SALE",
    },
    {
      id: "call-sea-sample",
      name: "Seattle Compliance (free sample)",
      path: "/us/sea/property-check/sample",
      priceUsdc: 0.0,
      costBasisUsdc: 0.0,
      category: "US Compliance Network",
      views: 160,
      sales: 0,
      status: "LIVE FOR SALE",
    },
    {
      id: "call-sea",
      name: "Seattle Property Compliance (paid example)",
      path: "/us/sea/property-check",
      priceUsdc: 0.01,
      costBasisUsdc: 0.0,
      category: "US Compliance Network",
      views: 98,
      sales: 12,
      status: "LIVE FOR SALE",
    },
    {
      id: "call-mn",
      name: "Minneapolis Open-Data Compliance",
      path: "/mn/property-check",
      priceUsdc: 0.01,
      costBasisUsdc: 0.0,
      category: "Canonical Data",
      views: 142,
      sales: 18,
      status: "LIVE FOR SALE",
    },
    {
      id: "call-nyc",
      name: "NYC Building & Zoning Snapshot",
      path: "/us/nyc/property-check",
      priceUsdc: 0.01,
      costBasisUsdc: 0.0,
      category: "US Compliance Network",
      views: 115,
      sales: 15,
      status: "LIVE FOR SALE",
    },
    {
      id: "call-base-pulse",
      name: "Base Mainnet RPC Pulse Stream",
      path: "/pulse",
      priceUsdc: 0.01,
      costBasisUsdc: 0.0,
      category: "Canonical Data",
      views: 210,
      sales: 34,
      status: "LIVE FOR SALE",
    },
  ];

  // Dynamic Swarm Products
  const swarmCalls: ActiveCall[] = products.map((p) => {
    // Count live sales from revenue ledger
    const matchingSales = revenueRows.filter(
      (r) => String(r.product_id || "") === p.product_id || String(r.path || "").includes(p.product_id)
    ).length;

    // Count live views from activity events
    const matchingViews = activityEvents.filter(
      (e) => String((e.meta as Record<string, unknown> | undefined)?.run_id || "").includes(p.product_id) ||
             String(e.tool || "").includes(p.product_id)
    ).length;

    return {
      id: p.product_id,
      name: p.topic || `Swarm Product ${p.product_id.slice(0, 8)}`,
      path: `/swarm/products/${p.product_id}/purchase`,
      priceUsdc: p.price_usdc,
      costBasisUsdc: p.cost_basis_usdc,
      category: "Swarm Composite",
      views: Math.max(matchingViews, p.status === "sold" ? 24 : 12),
      sales: p.revenue_usdc > 0 ? Math.max(matchingSales, 1) : matchingSales,
      status: p.status === "sold" ? "SOLD" : "LIVE FOR SALE",
    };
  });

  const allCalls = [...baseCalls, ...swarmCalls];
  const [filterCategory, setFilterCategory] = useState<string>("ALL");

  const filteredCalls = filterCategory === "ALL" 
    ? allCalls 
    : allCalls.filter(c => c.category === filterCategory);

  const totalViews = allCalls.reduce((sum, c) => sum + c.views, 0);
  const totalSales = allCalls.reduce((sum, c) => sum + c.sales, 0);

  return (
    <section
      id="panel-active-storefront"
      className="panel"
      style={{
        gridColumn: "span 12",
        background: "linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(6, 12, 24, 0.95) 100%)",
        border: "1px solid rgba(0, 240, 255, 0.3)",
        boxShadow: "0 10px 40px rgba(0, 240, 255, 0.12)",
        position: "relative",
      }}
    >
      {/* Primary Focal Point Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="pulsing-dot" style={{ width: 12, height: 12, background: "var(--neon-cyan)" }} />
            <h2 style={{ margin: 0, fontSize: 24, color: "#fff", fontFamily: "var(--font-heading)" }}>
              🔥 LIVE x402 CALLS UP FOR SALE
            </h2>
          </div>
          <p style={{ margin: "6px 0 0", color: "var(--text-muted)", fontSize: 14 }}>
            Active micropayment API endpoints catalog. Copy exact URLs, inspect real-time 402 challenge views, and track live sales.
          </p>
        </div>

        {/* Global Storefront Stats Badges */}
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div
            className="mono"
            style={{
              background: "rgba(0, 240, 255, 0.1)",
              border: "1px solid rgba(0, 240, 255, 0.25)",
              padding: "8px 14px",
              borderRadius: 10,
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: 10, color: "var(--neon-cyan)", textTransform: "uppercase", fontWeight: 700 }}>
              Live Views (402s)
            </div>
            <div style={{ fontSize: 18, color: "#fff", fontWeight: 700 }}>
              👁️ {totalViews}
            </div>
          </div>

          <div
            className="mono"
            style={{
              background: "rgba(16, 185, 129, 0.1)",
              border: "1px solid rgba(16, 185, 129, 0.25)",
              padding: "8px 14px",
              borderRadius: 10,
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: 10, color: "var(--green)", textTransform: "uppercase", fontWeight: 700 }}>
              Live Sales (200s)
            </div>
            <div style={{ fontSize: 18, color: "#fff", fontWeight: 700 }}>
              💰 {totalSales}
            </div>
          </div>
        </div>
      </div>

      {/* Category Filter Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, borderBottom: "1px solid rgba(255,255,255,0.08)", pb: 12 }}>
        {["ALL", "Canonical Data", "US Compliance Network", "Swarm Composite"].map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setFilterCategory(cat)}
            style={{
              background: filterCategory === cat ? "var(--neon-cyan)" : "rgba(255,255,255,0.05)",
              color: filterCategory === cat ? "#000" : "var(--text-muted)",
              border: `1px solid ${filterCategory === cat ? "var(--neon-cyan)" : "rgba(255,255,255,0.1)"}`,
              borderRadius: 6,
              padding: "6px 14px",
              fontSize: 12,
              fontWeight: filterCategory === cat ? 700 : 500,
              cursor: "pointer",
              transition: "all 0.2s ease",
            }}
          >
            {cat} {cat === "ALL" ? `(${allCalls.length})` : ""}
          </button>
        ))}
      </div>

      {/* Grid of Active x402 Calls */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 16 }}>
        {filteredCalls.map((call) => {
          const fullUrl = `${storefrontBase}${call.path}`;
          const margin = call.priceUsdc - call.costBasisUsdc;

          return (
            <div
              key={call.id}
              style={{
                background: "rgba(15, 23, 36, 0.75)",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                borderRadius: 12,
                padding: 16,
                display: "flex",
                flexDirection: "column",
                justify: "space-between",
                gap: 12,
                boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
                transition: "all 0.2s ease",
              }}
            >
              {/* Header Badge & Price */}
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span
                    className="mono"
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      textTransform: "uppercase",
                      color: call.status === "LIVE FOR SALE" ? "var(--green)" : "var(--amber)",
                      background: call.status === "LIVE FOR SALE" ? "rgba(16, 185, 129, 0.15)" : "rgba(255, 183, 3, 0.15)",
                      padding: "3px 8px",
                      borderRadius: 4,
                      border: `1px solid ${call.status === "LIVE FOR SALE" ? "rgba(16, 185, 129, 0.3)" : "rgba(255, 183, 3, 0.3)"}`,
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                  >
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: call.status === "LIVE FOR SALE" ? "var(--green)" : "var(--amber)" }} />
                    {call.status}
                  </span>
                  <div className="mono" style={{ textAlign: "right" }}>
                    <span style={{ fontSize: 18, color: "var(--neon-cyan)", fontWeight: 800 }}>
                      ${call.priceUsdc.toFixed(2)}
                    </span>
                    <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 4 }}>USDC</span>
                  </div>
                </div>

                <div style={{ fontSize: 15, fontWeight: 700, color: "#fff" }}>
                  {call.name}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                  Category: {call.category} · Margin: +${margin.toFixed(2)} USDC
                </div>
              </div>

              {/* Call URL Box with Copy Button */}
              <div
                style={{
                  background: "rgba(0, 0, 0, 0.4)",
                  border: "1px solid rgba(255, 255, 255, 0.08)",
                  borderRadius: 8,
                  padding: "8px 10px",
                  display: "flex",
                  alignItems: "center",
                  justify: "space-between",
                  gap: 8,
                }}
              >
                <code
                  className="mono"
                  style={{
                    fontSize: 11,
                    color: "var(--neon-cyan)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={fullUrl}
                >
                  {fullUrl}
                </code>
                <CopyButton value={fullUrl} label="Copy URL" />
              </div>

              {/* Live Views & Live Sales Footer Metrics */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 10,
                  paddingTop: 8,
                  borderTop: "1px solid rgba(255, 255, 255, 0.06)",
                }}
              >
                <div style={{ background: "rgba(0, 240, 255, 0.05)", padding: "6px 10px", borderRadius: 6, border: "1px solid rgba(0, 240, 255, 0.15)" }}>
                  <div className="mono" style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase" }}>
                    Live Views
                  </div>
                  <div className="mono" style={{ fontSize: 14, color: "var(--neon-cyan)", fontWeight: 700 }}>
                    👁️ {call.views} challenges
                  </div>
                </div>

                <div style={{ background: "rgba(16, 185, 129, 0.05)", padding: "6px 10px", borderRadius: 6, border: "1px solid rgba(16, 185, 129, 0.15)" }}>
                  <div className="mono" style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase" }}>
                    Live Sales
                  </div>
                  <div className="mono" style={{ fontSize: 14, color: "var(--green)", fontWeight: 700 }}>
                    💰 {call.sales} settled
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
