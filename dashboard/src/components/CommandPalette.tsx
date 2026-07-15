import { useEffect, useState } from "react";
import { CopyButton } from "./CopyButton";

export type PaletteAction = {
  id: string;
  label: string;
  run: () => void;
};

export function CommandPalette({
  open,
  onClose,
  actions,
  receiveAddress,
  vaultAddress,
}: {
  open: boolean;
  onClose: () => void;
  actions: PaletteAction[];
  receiveAddress?: string | null;
  vaultAddress?: string | null;
}) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  if (!open) return null;

  const q = query.toLowerCase();
  const filtered = actions.filter((a) => a.label.toLowerCase().includes(q));

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 20 }}
      onClick={onClose}
      role="dialog"
      aria-label="Command palette"
    >
      <div
        className="panel"
        style={{ margin: "10% auto", width: 440 }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3>Command palette</h3>
        <input
          autoFocus
          placeholder="Jump to panel, toggle demo…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ width: "100%", marginBottom: 8 }}
          aria-label="Palette search"
        />
        <ul style={{ listStyle: "none", padding: 0, margin: 0, maxHeight: 240, overflow: "auto" }}>
          {filtered.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                style={{ width: "100%", textAlign: "left", padding: "6px 0", background: "transparent", border: "none", color: "var(--text)", cursor: "pointer" }}
                onClick={() => {
                  a.run();
                  onClose();
                }}
              >
                {a.label}
              </button>
            </li>
          ))}
        </ul>
        <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
          {receiveAddress && <CopyButton value={receiveAddress} label="Receive addr" />}
          {vaultAddress && <CopyButton value={vaultAddress} label="Vault addr" />}
        </div>
      </div>
    </div>
  );
}