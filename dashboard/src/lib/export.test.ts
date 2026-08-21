import { describe, it, expect } from "vitest";
import { ledgerToCsv } from "./export";
import type { LedgerRow } from "../types/api";

describe("ledgerToCsv", () => {
  it("returns empty string for no rows", () => {
    expect(ledgerToCsv([])).toBe("");
  });

  it("generates CSV with headers", () => {
    const rows: LedgerRow[] = [
      {
        ts: "2026-01-01T00:00:00Z",
        amount_usdc: 0.01,
        amount_atomic: 10000,
        network: "eip155:84532",
        tx_hash: "0xabc",
        agent_id: "test-01",
        status: "settled",
      },
    ];
    const csv = ledgerToCsv(rows);
    const lines = csv.split("\n");
    expect(lines[0]).toBe("ts,amount_usdc,amount_atomic,network,tx_hash,agent_id,status");
    expect(lines[1]).toContain("2026-01-01");
    expect(lines[1]).toContain("0.01");
    expect(lines[1]).toContain("settled");
  });

  it("escapes commas in values", () => {
    const rows: LedgerRow[] = [
      {
        ts: "2026-01-01T00:00:00Z",
        agent_id: "agent,with,commas",
      },
    ];
    const csv = ledgerToCsv(rows);
    expect(csv).toContain('"agent,with,commas"');
  });
});
