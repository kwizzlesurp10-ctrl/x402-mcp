import { useMemo, useState } from "react";
import type { CityCatalogItem, DemandReport, LedgerRow, SwarmProduct } from "../api/client";
import type { StreamEvent } from "../hooks/useSSE";
import { CopyButton } from "./CopyButton";
import { demoCities } from "../fixtures/demo";
import { mergeStorefrontCalls, type ActiveCall } from "../utils/storefront";

import { API_BASE } from "../api/client";

export function ActiveStorefront({
  products,
  revenueRows = [],
  activityEvents: _activityEvents = [],
  cities = null,
  demand = null,
  demo = false,
}: {
  products: SwarmProduct[];
  revenueRows?: LedgerRow[];
  activityEvents?: StreamEvent[];
  cities?: CityCatalogItem[] | null;
  demand?: DemandReport | null;
  demo?: boolean;
}) {
  const origin = API_BASE || (typeof window !== "undefined" ? window.location.origin : "");

  const catalogCities = demo ? demoCities : cities;

  const allCalls = useMemo(
    () =>
      mergeStorefrontCalls({
        cities: catalogCities,
        demand,
        products,
        revenueRows,
      }),
    [catalogCities, demand, products, revenueRows],
  );

  const [filterCategory, setFilterCategory] = useState<string>("ALL");

  const filteredCalls =
    filterCategory === "ALL" ? allCalls : allCalls.filter((c) => c.category === filterCategory);

  const totalViews = allCalls.reduce((sum, c) => sum + c.views, 0);
  const totalSales = allCalls.reduce((sum, c) => sum + c.sales, 0);

  const formatPrice = (call: ActiveCall) =>
    call.priceUsdc.toLocaleString(undefined, {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

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

      <div style={{ display: "flex", gap: 8, marginBottom: 16, borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 12 }}>
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

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 16 }}>
        {filteredCalls.map((call) => {
          const fullUrl = `${origin}${call.path}`;
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
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                  <h3 style={{ margin: 0, fontSize: 16, color: "#fff" }}>{call.name}</h3>
                  <span
                    className="mono"
                    style={{
                      fontSize: 10,
                      padding: "4px 8px",
                      borderRadius: 6,
                      background: "rgba(16, 185, 129, 0.15)",
                      color: "var(--green)",
                      fontWeight: 700,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {call.status}
                  </span>
                </div>

                <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                  <span
                    className="mono"
                    style={{
                      fontSize: 18,
                      fontWeight: 700,
                      color: "var(--neon-cyan)",
                    }}
                  >
                    {formatPrice(call)}
                  </span>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>USDC</span>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>·</span>
                  <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    Network: Base eip155:8453
                  </span>
                </div>

                <p className="mono" style={{ margin: "10px 0 0", fontSize: 12, color: "var(--text-muted)", wordBreak: "break-all" }}>
                  {call.path}
                </p>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <div className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  👁️ {call.views} views · 💰 {call.sales} sales
                  {margin > 0 && (
                    <span style={{ marginLeft: 8 }}>margin {formatPrice({ ...call, priceUsdc: margin })}</span>
                  )}
                </div>
                <CopyButton value={fullUrl} label="Copy URL" />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
