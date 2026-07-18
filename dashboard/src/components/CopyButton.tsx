import { useState } from "react";

export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      type="button"
      className="mono"
      style={{ fontSize: 12, cursor: "pointer", background: "transparent", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 6, padding: "4px 8px" }}
      onClick={async () => {
        await navigator.clipboard.writeText(value);
        setOk(true);
        setTimeout(() => setOk(false), 1200);
      }}
      aria-label={`Copy ${label}`}
    >
      {ok ? "✓" : label}
    </button>
  );
}