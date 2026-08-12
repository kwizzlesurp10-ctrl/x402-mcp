import React, { useState } from "react";

interface ResourceProduct {
  id: string;
  name: string;
  category: string;
  priceUsdc: number;
  network: string;
  endpoint: string;
  description: string;
  seller: string;
}

/** Public storefront — never window.location (Mission Control SPA is not the API). */
const STOREFRONT_BASE = (
  import.meta.env.VITE_STOREFRONT_BASE_URL || "https://x402-mcp.onrender.com"
).replace(/\/$/, "");

const PRODUCTS: ResourceProduct[] = [
  {
    id: "us-city-catalog",
    name: "US City Open-Data Compliance Catalog",
    category: "Real Estate Open Data",
    priceUsdc: 0,
    network: "Base Mainnet (8453)",
    endpoint: "/us/cities",
    description:
      "Free machine catalog of 14-jurisdiction property compliance endpoints. Canonical Visit URL for Gold402/24K.",
    seller: "0xAB745e5F576667037696e78ba7dA28E193E4423D",
  },
  {
    id: "sea-property-check-sample",
    name: "Seattle RRIO free sample",
    category: "Real Estate Open Data",
    priceUsdc: 0,
    network: "Base Mainnet (8453)",
    endpoint: "/us/sea/property-check/sample",
    description: "Canonical free-sample Resource URL for the US city network",
    seller: "0xAB745e5F576667037696e78ba7dA28E193E4423D",
  },
  {
    id: "sea-property-check-01",
    name: "Seattle Property Compliance (paid example)",
    category: "Real Estate Open Data",
    priceUsdc: 0.01,
    network: "Base Mainnet (8453)",
    endpoint: "/us/sea/property-check",
    description:
      "Canonical paid Resource URL — Seattle RRIO rental registration via City of Seattle open data",
    seller: "0xAB745e5F576667037696e78ba7dA28E193E4423D",
  },
  {
    id: "4cc95d8e0d7b4c628d3afcab0edf32ae",
    name: "Base Network Pulse",
    category: "Live RPC Intelligence",
    priceUsdc: 0.05,
    network: "Base Mainnet (8453)",
    endpoint: "/swarm/products/4cc95d8e0d7b4c628d3afcab0edf32ae/purchase",
    description: "Live settlement-conditions intelligence (EIP-1559 gas math + block utilization + ETH spot price)",
    seller: "0xAB745e5F576667037696e78ba7dA28E193E4423D",
  },
  {
    id: "mn-property-check-01",
    name: "Minneapolis Rental Compliance",
    category: "Real Estate Open Data",
    priceUsdc: 0.01,
    network: "Base Mainnet (8453)",
    endpoint: "/mn/property-check?address=3500+Nicollet+Ave",
    description: "Rental compliance snapshot composed from live city open data and license records",
    seller: "0xAB745e5F576667037696e78ba7dA28E193E4423D",
  },
  {
    id: "ai-llm-inference-01",
    name: "Llama-3.3 70B Deep Reasoning",
    category: "AI Inference API",
    priceUsdc: 0.02,
    network: "Base Mainnet (8453)",
    endpoint: "/v1/chat/completions",
    description: "Accountless pay-per-prompt streaming LLM inference endpoint with token-level metering",
    seller: "0x91745e5F576667037696e78ba7dA28E193E4423E",
  },
  {
    id: "web-scraper-stealth-01",
    name: "Stealth Web Scraper & OCR",
    category: "Data Extraction",
    priceUsdc: 0.015,
    network: "Solana Mainnet",
    endpoint: "/scrape?url=https://news.ycombinator.com",
    description: "Headless browser DOM extraction with captcha bypass and clean Markdown output",
    seller: "solana:9A8B7C...",
  },
];

export function BazaarResourceExplorer({ density }: { density: string }) {
  const [selectedProductId, setSelectedProductId] = useState<string>(PRODUCTS[0].id);
  const [probeResult, setProbeResult] = useState<string | null>(null);
  const [probing, setProbing] = useState<boolean>(false);

  const selectedProduct = PRODUCTS.find((p) => p.id === selectedProductId) || PRODUCTS[0];

  const handleSimulateProbe = () => {
    setProbing(true);
    setProbeResult(null);
    const fullUrl = `${STOREFRONT_BASE}${selectedProduct.endpoint}`;

    setTimeout(() => {
      setProbing(false);
      setProbeResult(
        JSON.stringify(
          {
            status: 402,
            statusText: "Payment Required",
            headers: {
              "payment-required": "eyJ4NDAyVmVyc2lvbiI6MiwiZXJyb3IiOiJCYXNlIGdhcyBwcmljZS4uLiJ9",
            },
            body: {
              error: "payment_required",
              product_id: selectedProduct.id,
              topic: selectedProduct.name,
              price_usdc: selectedProduct.priceUsdc,
              network: selectedProduct.network,
              pay_to: selectedProduct.seller,
              resource_url: fullUrl,
              instructions: "Pay via x402 and retry with PAYMENT-SIGNATURE header.",
            },
          },
          null,
          2
        )
      );
    }, 500);
  };

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
            Discover and probe live HTTP 402 protected APIs
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
          1,420+ Listed Services
        </span>
      </div>

      {/* Product Selector List */}
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {PRODUCTS.map((prod) => {
          const isSelected = prod.id === selectedProductId;
          return (
            <div
              key={prod.id}
              onClick={() => {
                setSelectedProductId(prod.id);
                setProbeResult(null);
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
                justify: "space-between",
                alignItems: "center",
                transition: "all 0.15s ease-in-out",
              }}
            >
              <div>
                <div style={{ fontSize: "13px", fontWeight: 600, color: "#F3F4F6" }}>
                  {prod.name}
                </div>
                <div style={{ fontSize: "11px", color: "#9CA3AF" }}>
                  {prod.category} • <code style={{ color: "#60A5FA" }}>{prod.endpoint}</code>
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
                  ${prod.priceUsdc.toFixed(2)} USDC
                </div>
                <div style={{ fontSize: "10px", color: "#6B7280" }}>{prod.network}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected Product Detail & 402 Probe Inspector */}
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
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: "12px", color: "#9CA3AF" }}>{selectedProduct.description}</span>
          <button
            onClick={handleSimulateProbe}
            disabled={probing}
            style={{
              padding: "6px 12px",
              borderRadius: "6px",
              background: "linear-gradient(135deg, #00F0FF 0%, #3B82F6 100%)",
              border: "none",
              color: "#05070E",
              fontWeight: 600,
              fontSize: "11px",
              cursor: probing ? "wait" : "pointer",
            }}
          >
            {probing ? "Probing 402..." : "Probe 402 Challenge"}
          </button>
        </div>

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
