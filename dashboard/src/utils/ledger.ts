import type { LedgerRow } from "../api/client";
import { parseUsdcToAtomic } from "./usdc";

/** Read ledger amount as integer USDC atomic units — never float math at render. */
export function ledgerRowAtomic(row: LedgerRow): number {
  const direct = row.amount_usdc_atomic ?? row.amount_atomic;
  if (typeof direct === "number" && Number.isFinite(direct)) {
    return Math.trunc(direct);
  }
  if (typeof direct === "string" && /^\d+$/.test(direct)) {
    return Number(direct);
  }

  const nominal = row.nominal_usdc_atomic;
  if (typeof nominal === "number" && Number.isFinite(nominal)) {
    return Math.trunc(nominal);
  }

  const human = row.amount_usdc ?? row.nominal_usdc;
  if (human == null) return 0;
  const parsed = parseUsdcToAtomic(String(human));
  return parsed ?? 0;
}

export function sumLedgerAtomic(rows: LedgerRow[], mainnetOnly = false): number {
  return rows.reduce((acc, row) => {
    const network = String(row.network ?? "");
    if (mainnetOnly && network.includes("84532")) return acc;
    if (mainnetOnly && !network.includes("8453")) return acc;
    if (row.testnet === true && mainnetOnly) return acc;
    return acc + ledgerRowAtomic(row);
  }, 0);
}

export function ledgerToCsv(rows: LedgerRow[]): string {
  if (rows.length === 0) return "ts,amount_usdc_atomic,network,agent_id\n";
  const keys = Array.from(
    rows.reduce((set, row) => {
      Object.keys(row).forEach((k) => set.add(k));
      return set;
    }, new Set<string>()),
  );
  const header = keys.join(",");
  const lines = rows.map((row) =>
    keys
      .map((k) => {
        const v = row[k];
        const s = v == null ? "" : String(v);
        return s.includes(",") ? `"${s.replace(/"/g, '""')}"` : s;
      })
      .join(","),
  );
  return [header, ...lines].join("\n");
}

export function downloadText(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}