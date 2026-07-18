import { useState } from "react";
import { api } from "../api/client";
import { CopyButton } from "./CopyButton";
import { callsToBreakEven } from "../utils/breakEven";
import { formatUsdcAtomic } from "../utils/usdc";

const SEPOLIA = "eip155:84532";
const MAINNET = "eip155:8453";

export function SellerWizard({
  open,
  onClose,
  netAtomic,
  actionsEnabled,
}: {
  open: boolean;
  onClose: () => void;
  netAtomic: number;
  actionsEnabled: boolean;
}) {
  const [network, setNetwork] = useState(SEPOLIA);
  const [price, setPrice] = useState("$0.01");
  const [description, setDescription] = useState("Paid MCP-backed API access");
  const [mainnetConfirm, setMainnetConfirm] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const breakEvenCalls = callsToBreakEven(netAtomic, price);
  const mainnetBlocked = network === MAINNET && mainnetConfirm !== "eip155:8453";

  const mcpCommand = `build_seller_requirements(network="${network}", price="${price}", description="${description}")`;

  const fastApiSnippet = `from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.get("/paid")
async def paid_resource():
    raise HTTPException(
        status_code=402,
        detail={"payment": "requirements from build_seller_requirements"},
    )`;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        zIndex: 15,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      role="dialog"
      aria-label="Sell something wizard"
    >
      <div className="panel" style={{ width: 520, maxHeight: "85vh", overflow: "auto" }}>
        <h2>Sell something</h2>
        <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
          Build seller payment requirements. This does not move funds.
        </p>

        <label>
          Price
          <input value={price} onChange={(e) => setPrice(e.target.value)} style={{ width: "100%" }} />
        </label>
        <label style={{ display: "block", marginTop: 8 }}>
          Network
          <select value={network} onChange={(e) => setNetwork(e.target.value)} style={{ width: "100%" }}>
            <option value={SEPOLIA}>Base Sepolia (testnet)</option>
            <option value={MAINNET}>Base mainnet (real USDC)</option>
          </select>
        </label>
        {network === MAINNET && (
          <div style={{ marginTop: 8 }}>
            <p style={{ color: "var(--red)", fontSize: 13 }}>
              This spends real USDC on Base mainnet — up to {price} per call.
            </p>
            <label>
              Type <code>eip155:8453</code> to confirm
              <input
                value={mainnetConfirm}
                onChange={(e) => setMainnetConfirm(e.target.value)}
                style={{ width: "100%" }}
              />
            </label>
          </div>
        )}
        <label style={{ display: "block", marginTop: 8 }}>
          Description
          <input value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: "100%" }} />
        </label>

        <div style={{ marginTop: 12 }}>
          <strong>MCP invocation</strong>
          <pre className="mono" style={{ fontSize: 12 }}>{mcpCommand}</pre>
          <CopyButton value={mcpCommand} label="Copy MCP cmd" />
        </div>

        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <button
            type="button"
            disabled={mainnetBlocked}
            onClick={async () => {
              setError(null);
              if (!actionsEnabled) {
                setError("DASHBOARD_ACTIONS=false — copy the MCP command above or enable actions in server env.");
                return;
              }
              try {
                const res = await api.sellerRequirements({ network, price, description });
                setResult(res);
              } catch (e) {
                setError(e instanceof Error ? e.message : String(e));
              }
            }}
          >
            Build via API
          </button>
        </div>

        {error && <p style={{ color: "var(--red)", fontSize: 13 }}>{error}</p>}

        {result && (
          <div style={{ marginTop: 12 }}>
            <strong>Requirements JSON</strong>
            <pre className="mono" style={{ fontSize: 11, maxHeight: 160, overflow: "auto" }}>
              {JSON.stringify(result, null, 2)}
            </pre>
            <CopyButton value={JSON.stringify(result, null, 2)} label="Copy JSON" />
          </div>
        )}

        <div style={{ marginTop: 12 }}>
          <strong>Minimal FastAPI 402 gate</strong>
          <pre className="mono" style={{ fontSize: 11 }}>{fastApiSnippet}</pre>
          <CopyButton value={fastApiSnippet} label="Copy snippet" />
        </div>

        {breakEvenCalls != null && (
          <p style={{ fontSize: 13, color: "var(--amber)" }}>
            At {price}/call, {breakEvenCalls} verified calls covers the current gap (
            {formatUsdcAtomic(Math.abs(netAtomic))}).
          </p>
        )}

        <button type="button" style={{ marginTop: 12 }} onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}