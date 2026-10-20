/** CSV export utility for ledger data. */

import type { LedgerRow } from "../types/api";

export function ledgerToCsv(rows: LedgerRow[]): string {
  if (rows.length === 0) return "";

  const headers = ["ts", "amount_usdc", "amount_atomic", "network", "tx_hash", "agent_id", "status"];
  const lines = [headers.join(",")];

  for (const row of rows) {
    const values = headers.map((h) => {
      const val = row[h];
      if (val === undefined || val === null) return "";
      const str = String(val);
      return str.includes(",") || str.includes('"') ? `"${str.replace(/"/g, '""')}"` : str;
    });
    lines.push(values.join(","));
  }

  return lines.join("\n");
}

export function downloadCsv(rows: LedgerRow[], name: string): void {
  const csv = ledgerToCsv(rows);
  if (!csv) return;

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `x402-${name}-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
