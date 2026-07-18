import { describe, expect, it } from "vitest";
import { callsToBreakEven } from "./breakEven";

describe("callsToBreakEven", () => {
  it("uses parsed price not a hardcoded default", () => {
    const gap = -1_000_000; // -$1.00
    expect(callsToBreakEven(gap, "$0.01")).toBe(100);
    expect(callsToBreakEven(gap, "$1.00")).toBe(1);
  });

  it("returns null when net is non-negative", () => {
    expect(callsToBreakEven(0, "$0.01")).toBeNull();
    expect(callsToBreakEven(10_000, "$0.01")).toBeNull();
  });

  it("returns null for invalid price", () => {
    expect(callsToBreakEven(-10_000, "free")).toBeNull();
  });
});