import { useState } from "react";
import { isValidApiBase, writeStoredApiBase } from "../config";
import { setApiBase } from "../api/client";

type SettingsDialogProps = {
  open: boolean;
  apiBase: string;
  onClose: () => void;
  onSaved: (apiBase: string) => void;
};

const PRESETS = [
  { label: "Local API (dev proxy)", value: "/api" },
  { label: "Local API (direct)", value: "http://127.0.0.1:8402" },
  { label: "Production (example)", value: "https://x402-mcp.onrender.com" },
];

export function SettingsDialog({ open, apiBase, onClose, onSaved }: SettingsDialogProps) {
  const [draft, setDraft] = useState(apiBase);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const save = () => {
    const trimmed = draft.trim();
    if (!isValidApiBase(trimmed)) {
      setError("Enter a valid http(s) URL or /api dev proxy.");
      return;
    }
    writeStoredApiBase(trimmed);
    setApiBase(trimmed);
    onSaved(trimmed);
    onClose();
  };

  return (
    <div
      role="dialog"
      aria-label="API settings"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.75)",
        zIndex: 30,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      onClick={onClose}
    >
      <div
        className="panel mc-modal-panel"
        style={{ width: 520, padding: 20 }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ marginBottom: 8 }}>API base URL</h2>
        <p style={{ color: "var(--text-muted)", fontSize: 14, marginBottom: 12 }}>
          Mission Control admin talks to the x402-mcp FastAPI host. Use the dev proxy or a deployed URL.
        </p>
        <label style={{ display: "block", marginBottom: 8 }}>
          <span style={{ fontSize: 13 }}>Base URL</span>
          <input
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setError(null);
            }}
            style={{ width: "100%", marginTop: 4 }}
            placeholder="http://127.0.0.1:8402"
          />
        </label>
        {error && <p style={{ color: "var(--red)", fontSize: 13 }}>{error}</p>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "12px 0" }}>
          {PRESETS.map((p) => (
            <button key={p.value} type="button" onClick={() => setDraft(p.value)} style={{ fontSize: 12 }}>
              {p.label}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="button" onClick={save}>Save & reload data</button>
        </div>
      </div>
    </div>
  );
}
