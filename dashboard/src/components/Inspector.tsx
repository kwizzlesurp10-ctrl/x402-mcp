import { useState } from "react";
import { formatUsdc } from "../lib/format";
import { probeUrl } from "../hooks/useApi";
import type { ProbeResponse } from "../types/api";

interface InspectorProps {
  density: string;

}

type Tab = "probe" | "base64";

export function Inspector({ density }: InspectorProps) {
  const [tab, setTab] = useState<Tab>("probe");
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState("GET");
  const [probeResult, setProbeResult] = useState<ProbeResponse | null>(null);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [probing, setProbing] = useState(false);

  const [b64Input, setB64Input] = useState("");
  const [decoded, setDecoded] = useState<Record<string, unknown> | null>(null);
  const [decodeError, setDecodeError] = useState<string | null>(null);

  async function handleProbe() {
    if (!url.trim()) return;
    setProbing(true);
    setProbeError(null);
    setProbeResult(null);
    try {
      const result = await probeUrl(url, method);
      setProbeResult(result);
    } catch (e) {
      setProbeError(e instanceof Error ? e.message : "Probe failed");
    } finally {
      setProbing(false);
    }
  }

  function handleDecode() {
    setDecodeError(null);
    setDecoded(null);
    try {
      const raw = atob(b64Input.trim());
      const parsed = JSON.parse(raw);
      setDecoded(parsed);
    } catch {
      setDecodeError("Invalid base64 or JSON — check your PAYMENT-REQUIRED blob");
    }
  }

  return (
    <div className="panel" style={{ gridColumn: "1 / -1" }}>
      <div className="panel-title">
        402 Inspector
        {density === "guided" && (
          <span
            title="Inspect x402 payment requirements from a URL or a base64-encoded PAYMENT-REQUIRED header."
            style={{ cursor: "help", opacity: 0.6 }}
          >
            ?
          </span>
        )}
      </div>

      {/* Tab switcher */}
      <div style={{ display: "flex", gap: "4px", marginBottom: "12px" }}>
        <TabButton active={tab === "probe"} onClick={() => setTab("probe")}>
          Probe URL
        </TabButton>
        <TabButton active={tab === "base64"} onClick={() => setTab("base64")}>
          Raw Base64
        </TabButton>
      </div>

      {tab === "probe" && (
        <div>
          <div style={{ display: "flex", gap: "8px", marginBottom: "8px" }}>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              style={selectStyle}
              aria-label="HTTP method"
            >
              <option>GET</option>
              <option>POST</option>
              <option>PUT</option>
              <option>DELETE</option>
            </select>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://api.example.com/paid-resource"
              style={inputStyle}
              onKeyDown={(e) => e.key === "Enter" && handleProbe()}
              aria-label="URL to probe"
            />
            <button
              onClick={handleProbe}
              disabled={probing || !url.trim()}
              style={buttonStyle}
            >
              {probing ? "Probing…" : "Probe"}
            </button>
          </div>

          {probeError && (
            <div style={{ color: "var(--color-red)", fontSize: "13px", marginBottom: "8px" }}>
              {probeError}
            </div>
          )}

          {probeResult && <ProbeResultView result={probeResult} density={density} />}
        </div>
      )}

      {tab === "base64" && (
        <div>
          <textarea
            value={b64Input}
            onChange={(e) => setB64Input(e.target.value)}
            placeholder="Paste base64 PAYMENT-REQUIRED blob here…"
            style={{ ...inputStyle, minHeight: "80px", resize: "vertical", fontFamily: "var(--font-mono)", fontSize: "12px" }}
            aria-label="Base64 PAYMENT-REQUIRED blob"
          />
          <button
            onClick={handleDecode}
            disabled={!b64Input.trim()}
            style={{ ...buttonStyle, marginTop: "8px" }}
          >
            Decode
          </button>

          {decodeError && (
            <div style={{ color: "var(--color-red)", fontSize: "13px", marginTop: "8px" }}>
              {decodeError}
            </div>
          )}

          {decoded && <RequirementsTree data={decoded} density={density} />}
        </div>
      )}
    </div>
  );
}

function ProbeResultView({ result, density }: { result: ProbeResponse; density: string }) {
  const data = result.payment_required_decoded ?? result.payment_required_body;

  return (
    <div style={{ marginTop: "8px" }}>
      <div style={{ display: "flex", gap: "12px", alignItems: "center", marginBottom: "8px" }}>
        <span
          className={`chip ${result.payment_required ? "chip-testnet" : "chip-mainnet"}`}
          style={{ fontSize: "12px" }}
        >
          HTTP {result.status_code}
        </span>
        <span style={{ fontSize: "13px" }}>
          {result.payment_required
            ? "Payment required — x402 paywall detected"
            : "No payment required"}
        </span>
      </div>
      {data && <RequirementsTree data={data} density={density} />}
    </div>
  );
}

function RequirementsTree({ data, density }: { data: Record<string, unknown>; density: string }) {
  const accepts = (data.accepts ?? [data]) as Record<string, unknown>[];

  return (
    <div
      style={{
        background: "var(--color-base)",
        borderRadius: "6px",
        padding: "12px",
        fontSize: "12px",
        fontFamily: "var(--font-mono)",
        overflow: "auto",
        maxHeight: "300px",
        marginTop: "8px",
      }}
    >
      {accepts.map((req, i) => (
        <div key={i} style={{ marginBottom: i < accepts.length - 1 ? "12px" : 0 }}>
          {Object.entries(req).map(([key, value]) => {
            const isAmount =
              key === "maxAmountRequired" ||
              key === "amount" ||
              key === "maxAmount";
            const isPayTo = key === "payTo" || key === "payToAddress";
            const isNetwork = key === "network";

            let display = typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
            let color = "var(--color-text)";
            let extra = "";

            if (isAmount && typeof value === "string" || typeof value === "number") {
              const atomic = typeof value === "string" ? parseInt(value, 10) : value as number;
              color = "var(--color-usdc)";
              if (density !== "operator") {
                extra = ` (${formatUsdc(atomic)})`;
              }
            } else if (isPayTo) {
              color = "var(--color-green)";
            } else if (isNetwork) {
              color = "var(--color-amber)";
            }

            return (
              <div key={key} style={{ display: "flex", gap: "8px", lineHeight: "1.8" }}>
                <span style={{ color: "var(--color-text-muted)" }}>{key}:</span>
                <span style={{ color }}>
                  {display}
                  {extra && (
                    <span style={{ color: "var(--color-text-muted)", fontSize: "11px" }}>{extra}</span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        background: active ? "var(--color-border)" : "transparent",
        border: "1px solid var(--color-border)",
        borderRadius: "6px",
        color: active ? "var(--color-text)" : "var(--color-text-muted)",
        padding: "4px 12px",
        fontSize: "12px",
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

const inputStyle: React.CSSProperties = {
  flex: 1,
  background: "var(--color-base)",
  border: "1px solid var(--color-border)",
  borderRadius: "6px",
  color: "var(--color-text)",
  padding: "8px 12px",
  fontSize: "13px",
  outline: "none",
};

const selectStyle: React.CSSProperties = {
  background: "var(--color-base)",
  border: "1px solid var(--color-border)",
  borderRadius: "6px",
  color: "var(--color-text)",
  padding: "8px",
  fontSize: "13px",
  cursor: "pointer",
};

const buttonStyle: React.CSSProperties = {
  background: "var(--color-usdc)",
  border: "none",
  borderRadius: "6px",
  color: "white",
  padding: "8px 16px",
  fontSize: "13px",
  fontWeight: 500,
  cursor: "pointer",
};
