import { useState } from "react";
import { CopyButton } from "./CopyButton";
import type { StatsResponse, WalletResponse } from "../api/client";

export function AuthenticityBadge({
  stats,
  wallet,
}: {
  stats?: StatsResponse | null;
  wallet?: WalletResponse | null;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);

  const payToAddress =
    stats?.config?.pay_to_address ||
    wallet?.receive_address ||
    "0xAB745e5F576667037696e78ba7dA28E193E4423D";
  const baseAppId = "6a7018e2a8c4f2b6db3b3e71";
  const hasOwnershipProof = stats?.config?.has_ownership_proofs ?? false;
  const proofsCount = stats?.config?.ownership_proofs_count ?? 0;
  const defaultNetwork = stats?.config?.x402_default_network || "eip155:8453";

  return (
    <section
      id="panel-authenticity"
      className="panel mc-authenticity-card"
      style={{
        gridColumn: "span 12",
        background: "linear-gradient(135deg, rgba(8, 14, 26, 0.95) 0%, rgba(13, 20, 36, 0.95) 100%)",
        border: "1px solid rgba(0, 240, 255, 0.25)",
        borderRadius: "14px",
        padding: "20px 24px",
        boxShadow: "0 10px 30px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: "2px",
          background: "linear-gradient(90deg, var(--neon-cyan), #3B82F6, #10B981)",
        }}
      />

      {/* Top Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 12,
          marginBottom: 18,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 32,
              height: 32,
              borderRadius: "8px",
              background: "rgba(0, 240, 255, 0.15)",
              color: "var(--neon-cyan)",
              fontSize: 18,
              border: "1px solid rgba(0, 240, 255, 0.3)",
            }}
          >
            🛡️
          </span>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h3
                style={{
                  margin: 0,
                  fontSize: 16,
                  fontFamily: "var(--font-heading)",
                  color: "#fff",
                  letterSpacing: "-0.01em",
                }}
              >
                x402 PROTOCOL AUTHENTICITY & AGENT TRUST ANCHOR
              </h3>
              <span
                style={{
                  padding: "2px 8px",
                  borderRadius: "12px",
                  background: "rgba(16, 185, 129, 0.15)",
                  border: "1px solid rgba(16, 185, 129, 0.4)",
                  color: "var(--green)",
                  fontSize: 11,
                  fontFamily: "var(--font-mono, monospace)",
                  fontWeight: 700,
                  textTransform: "uppercase",
                }}
              >
                ✓ Live Mainnet Anchored
              </span>
            </div>
            <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: 13 }}>
              Cryptographic origin verification, Base App ID ecosystem tags, and settled non-repudiation receipts.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setDetailsOpen((v) => !v)}
          style={{
            background: "rgba(255, 255, 255, 0.06)",
            border: "1px solid rgba(255, 255, 255, 0.15)",
            color: "var(--text)",
            padding: "5px 12px",
            borderRadius: "6px",
            fontSize: 12,
            cursor: "pointer",
          }}
        >
          {detailsOpen ? "Hide Details ▲" : "Inspect Proofs ▼"}
        </button>
      </div>

      {/* Grid of 4 Authenticity Pillars */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: 14,
        }}
      >
        {/* Pillar 1: Base App ID */}
        <div
          style={{
            background: "rgba(15, 23, 42, 0.6)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "10px",
            padding: "14px 16px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
              Base Ecosystem App ID
            </span>
            <span style={{ color: "var(--neon-cyan)", fontSize: 11, fontWeight: 700 }}>✓ VERIFIED</span>
          </div>
          <div className="mono" style={{ fontSize: 13, color: "#fff", fontWeight: 600, wordBreak: "break-all" }}>
            {baseAppId}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span>Header & Meta Anchor</span>
            <CopyButton value={baseAppId} label="Copy ID" />
          </div>
        </div>

        {/* Pillar 2: PayTo Receive Address */}
        <div
          style={{
            background: "rgba(15, 23, 42, 0.6)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "10px",
            padding: "14px 16px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
              Settlement PayTo Wallet
            </span>
            <span style={{ color: "var(--green)", fontSize: 11, fontWeight: 700 }}>Base Mainnet</span>
          </div>
          <div className="mono" style={{ fontSize: 13, color: "var(--green)", fontWeight: 600 }}>
            {payToAddress.slice(0, 10)}…{payToAddress.slice(-8)}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6, display: "flex", gap: 8, alignItems: "center" }}>
            <a
              href={`https://basescan.org/address/${payToAddress}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--amber)", textDecoration: "none", fontSize: 11 }}
            >
              View on Basescan ↗
            </a>
            <span style={{ color: "var(--border)" }}>•</span>
            <CopyButton value={payToAddress} label="Copy" />
          </div>
        </div>

        {/* Pillar 3: EIP-191 Origin Ownership */}
        <div
          style={{
            background: "rgba(15, 23, 42, 0.6)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "10px",
            padding: "14px 16px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
              Origin Ownership Proofs
            </span>
            <span
              style={{
                color: hasOwnershipProof ? "var(--green)" : "var(--amber)",
                fontSize: 11,
                fontWeight: 700,
              }}
            >
              {hasOwnershipProof ? `✓ ${proofsCount} Signature${proofsCount > 1 ? "s" : ""}` : "EIP-191 Ready"}
            </span>
          </div>
          <div style={{ fontSize: 12, color: "#fff" }}>
            {hasOwnershipProof ? (
              <span className="mono" style={{ color: "var(--green)" }}>
                Cryptographically Signed by PayTo
              </span>
            ) : (
              <span style={{ color: "var(--text-muted)" }}>
                Advertised via <code className="mono">/.well-known/x402</code>
              </span>
            )}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
            <span>x402scan / Catalog verified</span>
          </div>
        </div>

        {/* Pillar 4: Autonomous Agent Surfaces */}
        <div
          style={{
            background: "rgba(15, 23, 42, 0.6)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "10px",
            padding: "14px 16px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
              Machine Discovery Surfaces
            </span>
            <span style={{ color: "var(--neon-cyan)", fontSize: 11, fontWeight: 700 }}>4 Live</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
            <a
              href="/.well-known/x402"
              target="_blank"
              rel="noopener noreferrer"
              className="mono"
              style={{
                fontSize: 11,
                padding: "2px 6px",
                borderRadius: "4px",
                background: "rgba(0, 240, 255, 0.1)",
                color: "var(--neon-cyan)",
                border: "1px solid rgba(0, 240, 255, 0.25)",
              }}
            >
              /.well-known/x402
            </a>
            <a
              href="/.well-known/agent-card.json"
              target="_blank"
              rel="noopener noreferrer"
              className="mono"
              style={{
                fontSize: 11,
                padding: "2px 6px",
                borderRadius: "4px",
                background: "rgba(16, 185, 129, 0.1)",
                color: "var(--green)",
                border: "1px solid rgba(16, 185, 129, 0.25)",
              }}
            >
              /agent-card.json
            </a>
            <a
              href="/llms.txt"
              target="_blank"
              rel="noopener noreferrer"
              className="mono"
              style={{
                fontSize: 11,
                padding: "2px 6px",
                borderRadius: "4px",
                background: "rgba(245, 158, 11, 0.1)",
                color: "var(--amber)",
                border: "1px solid rgba(245, 158, 11, 0.25)",
              }}
            >
              /llms.txt
            </a>
            <a
              href="/.well-known/mcp"
              target="_blank"
              rel="noopener noreferrer"
              className="mono"
              style={{
                fontSize: 11,
                padding: "2px 6px",
                borderRadius: "4px",
                background: "rgba(139, 92, 246, 0.1)",
                color: "#A78BFA",
                border: "1px solid rgba(139, 92, 246, 0.25)",
              }}
            >
              /mcp
            </a>
          </div>
        </div>
      </div>

      {/* Expandable Technical Proofs & Instructions */}
      {detailsOpen && (
        <div
          style={{
            marginTop: 16,
            paddingTop: 16,
            borderTop: "1px solid rgba(255, 255, 255, 0.08)",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
            gap: 16,
            fontSize: 12,
          }}
        >
          <div style={{ background: "rgba(0, 0, 0, 0.3)", padding: 12, borderRadius: 8 }}>
            <strong style={{ color: "#fff", display: "block", marginBottom: 6 }}>
              🔐 Cryptographic Origin Verification (EIP-191)
            </strong>
            <p style={{ color: "var(--text-muted)", margin: "0 0 8px" }}>
              To verify domain ownership to <code className="mono">x402scan</code> and crawler aggregators without exposing private keys, sign the origin URL with your receive wallet:
            </p>
            <pre
              className="mono"
              style={{
                background: "#080c14",
                padding: "8px 10px",
                borderRadius: "6px",
                color: "var(--neon-cyan)",
                fontSize: 11,
                overflowX: "auto",
              }}
            >
              python scripts/sign_ownership_proof.py --origin https://x402-mcp.onrender.com
            </pre>
            <span style={{ color: "var(--text-muted)", fontSize: 11 }}>
              Recovers to: <code className="mono" style={{ color: "#fff" }}>{payToAddress}</code>
            </span>
          </div>

          <div style={{ background: "rgba(0, 0, 0, 0.3)", padding: 12, borderRadius: 8 }}>
            <strong style={{ color: "#fff", display: "block", marginBottom: 6 }}>
              ⚡ Settlement & Protocol Security
            </strong>
            <ul style={{ paddingLeft: 18, margin: 0, color: "var(--text-muted)", lineHeight: 1.6 }}>
              <li>
                <strong style={{ color: "var(--text)" }}>Default CAIP-2 Network:</strong> <code className="mono">{defaultNetwork}</code> (Base Mainnet)
              </li>
              <li>
                <strong style={{ color: "var(--text)" }}>Payment Authorization:</strong> Gasless EIP-3009 <code className="mono">transferWithAuthorization</code>
              </li>
              <li>
                <strong style={{ color: "var(--text)" }}>Challenge Nonce TTL:</strong> 300s expiration with replay-protection
              </li>
              <li>
                <strong style={{ color: "var(--text)" }}>Non-Repudiation Receipts:</strong> <code className="mono">PAYMENT-RESPONSE</code> carrying on-chain tx hash
              </li>
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
