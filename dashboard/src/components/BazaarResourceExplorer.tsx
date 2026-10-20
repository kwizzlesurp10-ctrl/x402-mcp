import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type CityCatalogItem, type DemandReport, type LedgerRow, type SwarmProduct } from "../api/client";
import { demoCities } from "../fixtures/demo";
import { buildBazaarCatalog, DEFAULT_PAY_TO, type BazaarEntry } from "../utils/storefront";

/** Public storefront — never window.location (Mission Control SPA is not the API). */
const STOREFRONT_BASE = (
  import.meta.env.VITE_STOREFRONT_BASE_URL || "https://x402-mcp.onrender.com"
).replace(/\/$/, "");

type Props = {
  density: string;
  demo?: boolean;
  products?: SwarmProduct[];
  revenueRows?: LedgerRow[];
  payTo?: string;
};

export function BazaarResourceExplorer({
  density,
  demo = false,
  products = [],
  revenueRows = [],
  payTo = DEFAULT_PAY_TO,
}: Props) {
  const [cities, setCities] = useState<CityCatalogItem[] | null>(null);
  const [demand, setDemand] = useState<DemandReport | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string>("us-city-catalog");
  const [probeResult, setProbeResult] = useState<string | null>(null);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [probing, setProbing] = useState(false);

  useEffect(() => {
    if (demo) {
      setCities(demoCities);
      setDemand(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const [catalog, demandReport] = await Promise.all([api.usCities(), api.demand()]);
        if (!cancelled) {
          setCities(catalog.cities);
          setDemand(demandReport);
        }
      } catch {
        if (!cancelled) {
          setCities(null);
          setDemand(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [demo]);

  const entries = useMemo(
    () =>
      buildBazaarCatalog({
        cities: demo ? demoCities : cities,
        demand,
        products,
        revenueRows,
      }),
    [cities, demand, demo, products, revenueRows],
  );

  useEffect(() => {
    if (entries.length === 0) return;
    if (!entries.some((e) => e.id === selectedProductId)) {
      setSelectedProductId(entries[0].id);
    }
  }, [entries, selectedProductId]);

  const selectedProduct: BazaarEntry =
    entries.find((e) => e.id === selectedProductId) ?? entries[0];

  const handleProbe = useCallback(async () => {
    if (!selectedProduct) return;
    setProbing(true);
    setProbeResult(null);
    setProbeError(null);
    const fullUrl = `${STOREFRONT_BASE}${selectedProduct.path}`;
    try {
      const result = await api.probe(fullUrl);
      setProbeResult(JSON.stringify(result, null, 2));
    } catch (err) {
      setProbeError(err instanceof Error ? err.message : "Probe failed");
    } finally {
      setProbing(false);
    }
  }, [selectedProduct]);

  if (!selectedProduct) {
    return null;
  }

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
            x402 Bazaar Paid Resource Catalog
          </div>
          <div style={{ fontSize: "12px", color: "#9CA3AF" }}>
            Live listings from this storefront — cities + swarm composites
          </div>
        </div>
        <span
          style={{
            fontSize: "11px",
            fontFamily: "var(--font-mono, monospace)",
            padding: "4px 8px",
            borderRadius: "6px",
            background: "rgba(16, 185, 129, 0.1)",
            border: "1px solid rgba(16, 185, 129, 0.25)",
            color: "#10B981",
          }}
        >
          {entries.length} listed here
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "8px", maxHeight: 280, overflow: "auto" }}>
        {entries.map((prod) => {
          const isSelected = prod.id === selectedProductId;
          return (
            <div
              key={prod.id}
              role="button"
              tabIndex={0}
              onClick={() => {
                setSelectedProductId(prod.id);
                setProbeResult(null);
                setProbeError(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setSelectedProductId(prod.id);
                  setProbeResult(null);
                  setProbeError(null);
                }
              }}
              style={{
                padding: "10px 12px",
                borderRadius: "8px",
                cursor: "pointer",
                background: isSelected ? "rgba(0, 240, 255, 0.08)" : "rgba(255, 255, 255, 0.02)",
                border: isSelected
                  ? "1px solid rgba(0, 240, 255, 0.4)"
                  : "1px solid rgba(255, 255, 255, 0.05)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                transition: "all 0.15s ease-in-out",
              }}
            >
              <div>
                <div style={{ fontSize: "13px", fontWeight: 600, color: "#F3F4F6" }}>
                  {prod.name}
                </div>
                <div style={{ fontSize: "11px", color: "#9CA3AF" }}>
                  {prod.category} • <code style={{ color: "#60A5FA" }}>{prod.path}</code>
                </div>
              </div>

              <div style={{ textAlign: "right" }}>
                <div
                  style={{
                    fontSize: "13px",
                    fontWeight: 700,
                    color: "#10B981",
                    fontFamily: "var(--font-mono, monospace)",
                  }}
                >
                  {prod.priceUsdc === 0 ? "Free" : `$${prod.priceUsdc.toFixed(2)} USDC`}
                </div>
                <div style={{ fontSize: "10px", color: "#6B7280" }}>{prod.network}</div>
              </div>
            </div>
          );
        })}
      </div>

      <div
        style={{
          padding: "12px",
          borderRadius: "8px",
          background: "rgba(5, 7, 14, 0.8)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          display: "flex",
          flexDirection: "column",
          gap: "8px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: "12px", color: "#9CA3AF" }}>{selectedProduct.description}</span>
          <button
            type="button"
            onClick={() => void handleProbe()}
            disabled={probing || demo}
            title={demo ? "Disable Demo to probe the live storefront" : undefined}
            style={{
              padding: "6px 12px",
              borderRadius: "6px",
              background: "linear-gradient(135deg, #00F0FF 0%, #3B82F6 100%)",
              border: "none",
              color: "#05070E",
              fontWeight: 600,
              fontSize: "11px",
              cursor: probing || demo ? "not-allowed" : "pointer",
              opacity: demo ? 0.5 : 1,
              flexShrink: 0,
            }}
          >
            {probing ? "Probing…" : "Probe 402 Challenge"}
          </button>
        </div>
        <div style={{ fontSize: "10px", color: "#6B7280", fontFamily: "var(--font-mono, monospace)" }}>
          payTo: {payTo}
        </div>

        {probeError && (
          <pre
            style={{
              margin: 0,
              padding: "10px",
              borderRadius: "6px",
              background: "#090D16",
              border: "1px solid rgba(239, 68, 68, 0.35)",
              color: "#FCA5A5",
              fontSize: "11px",
              fontFamily: "var(--font-mono, monospace)",
              maxHeight: "140px",
              overflow: "auto",
            }}
          >
            {probeError}
          </pre>
        )}

        {probeResult && (
          <pre
            style={{
              margin: 0,
              padding: "10px",
              borderRadius: "6px",
              background: "#090D16",
              border: "1px solid rgba(0, 240, 255, 0.2)",
              color: "#00F0FF",
              fontSize: "11px",
              fontFamily: "var(--font-mono, monospace)",
              maxHeight: "140px",
              overflow: "auto",
            }}
          >
            {probeResult}
          </pre>
        )}
      </div>
    </div>
  );
}
