import { describe, expect, it } from "vitest";
import { ledgerRowAtomic, sumLedgerAtomic, ledgerToCsv } from "./ledger";

describe("ledgerRowAtomic", () => {
  it("prefers amount_usdc_atomic integer", () => {
    expect(ledgerRowAtomic({ amount_usdc_atomic: 10_000 })).toBe(10_000);
  });

  it("parses human amount without render-time float multiply", () => {
    expect(ledgerRowAtomic({ amount_usdc: "0.01" })).toBe(10_000);
  });
});

describe("sumLedgerAtomic", () => {
  it("excludes testnet from mainnet spend sum", () => {
    const rows = [
      { network: "eip155:84532", amount_usdc_atomic: 10_000, testnet: true },
      { network: "eip155:8453", amount_usdc_atomic: 5_000 },
    ];
    expect(sumLedgerAtomic(rows, true)).toBe(5_000);
  });
});

describe("ledgerToCsv", () => {
  it("emits header and row", () => {
    const csv = ledgerToCsv([{ ts: "2026-01-01", amount_usdc_atomic: 100 }]);
    expect(csv).toContain("amount_usdc_atomic");
    expect(csv).toContain("2026-01-01");
  });
});