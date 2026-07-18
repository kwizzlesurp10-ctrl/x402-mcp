import { describe, expect, it } from "vitest";
import { extractAtomicFrom402, formatUsdcAtomic, parseUsdcToAtomic } from "./usdc";

describe("formatUsdcAtomic", () => {
  it("formats six-decimal atomic units", () => {
    expect(formatUsdcAtomic(10_000)).toBe("$0.01");
    expect(formatUsdcAtomic(1_000_000)).toBe("$1.00");
    expect(formatUsdcAtomic(0)).toBe("$0.00");
  });

  it("handles null", () => {
    expect(formatUsdcAtomic(null)).toBe("—");
  });
});

describe("parseUsdcToAtomic", () => {
  it("parses human amounts", () => {
    expect(parseUsdcToAtomic("$0.01")).toBe(10_000);
    expect(parseUsdcToAtomic("1.5")).toBe(1_500_000);
  });
});

describe("extractAtomicFrom402", () => {
  it("reads maxAmountRequired string", () => {
    expect(extractAtomicFrom402({ maxAmountRequired: "10000" })).toBe(10_000);
  });
});