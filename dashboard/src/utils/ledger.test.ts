import { describe, expect, it } from "vitest";
import { isVerifiedRevenueRow, ledgerRowAtomic, sumLedgerAtomic, ledgerToCsv } from "./ledger";
import { calculateFinances } from "./finance";

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
describe("isVerifiedRevenueRow", () => {
  const hash = "0x" + "ab".repeat(32);
  it("trusts the server annotation", () => {
    expect(isVerifiedRevenueRow({ counts_as_revenue: true })).toBe(true);
    expect(isVerifiedRevenueRow({ counts_as_revenue: false, tx: hash, network: "eip155:8453", is_operator_settle: false })).toBe(false);
  });
  it("falls back to client rules for older servers", () => {
    expect(isVerifiedRevenueRow({ tx: hash, network: "eip155:8453", is_operator_settle: false })).toBe(true);
    expect(isVerifiedRevenueRow({ tx: "0xdeadbeef", network: "eip155:8453", is_operator_settle: false })).toBe(false);
    expect(isVerifiedRevenueRow({ tx: hash, network: "eip155:84532", is_operator_settle: false })).toBe(false);
    expect(isVerifiedRevenueRow({ tx: hash, network: "eip155:8453", is_operator_settle: true })).toBe(false);
    expect(isVerifiedRevenueRow({ tx: hash, network: "eip155:8453", is_operator_settle: null })).toBe(false);
  });
});

describe("calculateFinances", () => {
  it("counts only verified rows as gross revenue", () => {
    const rows = [
      { counts_as_revenue: true, amount_usdc_atomic: 10_000 },
      { counts_as_revenue: false, amount_usdc_atomic: 50_000 },
    ];
    const f = calculateFinances(rows, []);
    expect(f.grossRevenueAtomic).toBe(10_000);
    expect(f.rawRevenueAtomic).toBe(60_000);
    expect(f.excludedRevenueAtomic).toBe(50_000);
    expect(f.settlementCount).toBe(1);
  });
});
