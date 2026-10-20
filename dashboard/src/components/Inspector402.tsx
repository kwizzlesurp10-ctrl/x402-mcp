import { useState } from "react";
import { api } from "../api/client";
import { CopyButton } from "./CopyButton";
import { PanelHelp } from "./PanelHelp";
import { decodePaymentRequiredBase64 } from "../utils/decode402";
import { extractAtomicFrom402, formatUsdcAtomic } from "../utils/usdc";

type Tab = "url" | "base64" | "a2a";

export function Inspector402({
  onProbed,
}: {
  onProbed: (result: Record<string, unknown> | null) => void;
}) {
  const [tab, setTab] = useState<Tab>("url");
  const [probeUrl, setProbeUrl] = useState("");
  const [probeResult, setProbeResult] = useState<Record<string, unknown> | null>(null);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [b64Input, setB64Input] = useState("");
  const [b64Tree, setB64Tree] = useState<unknown>(null);
  const [b64Error, setB64Error] = useState<string | null>(null);
  const [a2aUrl, setA2aUrl] = useState("");
  const [a2aResult, setA2aResult] = useState<Record<string, unknown> | null>(null);
  const [a2aError, setA2aError] = useState<string | null>(null);
  const [a2aLoading, setA2aLoading] = useState(false);

  const scoutReport = probeResult
    ? JSON.stringify(probeResult, null, 2)
    : a2aResult
      ? JSON.stringify(a2aResult, null, 2)
      : b64Tree
        ? JSON.stringify(b64Tree, null, 2)
        : "";

  return (
    <div>
      <h3>
        402 & A2A Inspector <PanelHelp term="402" title="402 & A2A Inspector" />
      </h3>
      <div role="tablist" style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <button type="button" role="tab" aria-selected={tab === "url"} onClick={() => setTab("url")}>
          Probe URL
        </button>
        <button type="button" role="tab" aria-selected={tab === "base64"} onClick={() => setTab("base64")}>
          Raw base64
        </button>
        <button type="button" role="tab" aria-selected={tab === "a2a"} onClick={() => setTab("a2a")}>
          A2A Agent Card
        </button>
      </div>

      {tab === "url" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
            <input
              style={{ flex: 1 }}
              placeholder="https://api.example.com/paid"
              value={probeUrl}
              onChange={(e) => setProbeUrl(e.target.value)}
              aria-label="URL to probe"
            />
            <button
              type="button"
              onClick={async () => {
                setProbeError(null);
                try {
                  const result = await api.probe(probeUrl);
                  setProbeResult(result);
                  onProbed(result);
                } catch (e) {
                  const msg = e instanceof Error ? e.message : String(e);
                  setProbeError(msg);
                  setProbeResult(null);
                  onProbed(null);
                }
              }}
            >
              Probe
            </button>
          </div>
          {probeError && (
            <p style={{ color: "var(--red)", fontSize: 13 }}>
              {probeError} — use a public http(s) URL; private IPs are blocked.
            </p>
          )}
          {probeResult && (
            <div>
              {"payment_required_decoded" in probeResult && probeResult.payment_required_decoded != null && (
                <div className="mono" style={{ marginBottom: 8 }}>
                  Payment demanded:{" "}
                  {formatUsdcAtomic(extractAtomicFrom402(probeResult.payment_required_decoded))}
                  <span style={{ color: "var(--text-muted)", marginLeft: 8 }}>
                    ({extractAtomicFrom402(probeResult.payment_required_decoded)} atomic)
                  </span>
                </div>
              )}
              <pre className="mono" style={{ fontSize: 12, maxHeight: 200, overflow: "auto" }}>
                {JSON.stringify(probeResult, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {tab === "base64" && (
        <div>
          <textarea
            style={{ width: "100%", minHeight: 80 }}
            placeholder="Paste PAYMENT-REQUIRED base64"
            value={b64Input}
            onChange={(e) => setB64Input(e.target.value)}
            aria-label="PAYMENT-REQUIRED base64"
          />
          <button
            type="button"
            onClick={() => {
              try {
                const decoded = decodePaymentRequiredBase64(b64Input);
                setB64Tree(decoded);
                setB64Error(null);
              } catch (e) {
                setB64Error(e instanceof Error ? e.message : String(e));
                setB64Tree(null);
              }
            }}
          >
            Decode
          </button>
          {b64Error && <p style={{ color: "var(--red)", fontSize: 13 }}>{b64Error}</p>}
          {b64Tree != null && (
            <pre className="mono" style={{ fontSize: 12, maxHeight: 200, overflow: "auto" }}>
              {JSON.stringify(b64Tree, null, 2)}
            </pre>
          )}
        </div>
      )}

      {tab === "a2a" && (
        <div>
          <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
            <input
              style={{ flex: 1 }}
              placeholder="https://x402-mcp.onrender.com or target domain"
              value={a2aUrl}
              onChange={(e) => setA2aUrl(e.target.value)}
              aria-label="Agent URL to resolve"
            />
            <button
              type="button"
              disabled={a2aLoading}
              onClick={async () => {
                setA2aError(null);
                setA2aLoading(true);
                try {
                  const result = await api.a2aResolve(a2aUrl);
                  setA2aResult(result);
                } catch (e) {
                  const msg = e instanceof Error ? e.message : String(e);
                  setA2aError(msg);
                  setA2aResult(null);
                } finally {
                  setA2aLoading(false);
                }
              }}
            >
              {a2aLoading ? "Resolving…" : "Resolve Card"}
            </button>
          </div>
          {a2aError && (
            <p style={{ color: "var(--red)", fontSize: 13 }}>
              {a2aError} — SSRF protection active (private IPs blocked).
            </p>
          )}
          {a2aResult && (
            <div>
              <div className="mono" style={{ marginBottom: 8, display: "flex", gap: 12, flexWrap: "wrap", fontSize: 12 }}>
                <span>Status: <strong style={{ color: a2aResult.status === "valid" ? "var(--green)" : "var(--amber)" }}>{String(a2aResult.status)}</strong></span>
                {Boolean(a2aResult.has_ap2_extension) && (
                  <span style={{ color: "var(--green)" }}>AP2 v1 ✓</span>
                )}
                {Boolean(a2aResult.has_x402_extension) && (
                  <span style={{ color: "var(--neon-cyan, #00f0ff)" }}>A2A-x402 ✓</span>
                )}
                {Boolean(a2aResult.pay_to) && (
                  <span style={{ color: "var(--text-muted)" }}>payTo: {String(a2aResult.pay_to).slice(0, 10)}…</span>
                )}
              </div>
              <pre className="mono" style={{ fontSize: 12, maxHeight: 200, overflow: "auto" }}>
                {JSON.stringify(a2aResult, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {scoutReport && <CopyButton value={scoutReport} label="Copy scout report" />}
    </div>
  );
}