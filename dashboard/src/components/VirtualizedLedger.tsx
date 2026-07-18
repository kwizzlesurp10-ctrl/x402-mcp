import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { LedgerRow } from "../api/client";
import { CopyButton } from "./CopyButton";
import { basescanUrl, truncateHash } from "../utils/decode402";
import { ledgerRowAtomic } from "../utils/ledger";
import { formatUsdcAtomic } from "../utils/usdc";
import { relativeTime } from "../utils/time";

type Props = {
  rows: LedgerRow[];
  kind: "spend" | "revenue";
  filterNetwork?: string;
  filterAgent?: string;
};

export function VirtualizedLedger({ rows, kind, filterNetwork, filterAgent }: Props) {
  const parentRef = useRef<HTMLDivElement>(null);
  const filtered = rows.filter((row) => {
    if (filterNetwork && String(row.network ?? "") !== filterNetwork) return false;
    if (filterAgent && String(row.agent_id ?? "") !== filterAgent) return false;
    return true;
  });

  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 28,
    overscan: 8,
  });

  const color = kind === "spend" ? "var(--usdc)" : "var(--green)";

  return (
    <div ref={parentRef} style={{ maxHeight: 220, overflow: "auto" }}>
      <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
        {virtualizer.getVirtualItems().map((item) => {
          const row = filtered[item.index];
          const atomic = ledgerRowAtomic(row);
          const ts = String(row.ts ?? "");
          const tx = row.tx ? String(row.tx) : null;
          const network = String(row.network ?? "");
          return (
            <div
              key={item.key}
              className="mono"
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                height: item.size,
                transform: `translateY(${item.start}px)`,
                fontSize: 12,
                display: "flex",
                alignItems: "center",
                gap: 8,
                justifyContent: "space-between",
              }}
            >
              <span title={ts}>{relativeTime(ts)}</span>
              <span style={{ color }} title={`${atomic} atomic`}>
                {formatUsdcAtomic(atomic)}
              </span>
              {tx ? (
                <a href={basescanUrl(network, tx)} target="_blank" rel="noreferrer">
                  {truncateHash(tx)}
                </a>
              ) : (
                <span />
              )}
              {tx && <CopyButton value={tx} label="Tx" />}
            </div>
          );
        })}
      </div>
    </div>
  );
}