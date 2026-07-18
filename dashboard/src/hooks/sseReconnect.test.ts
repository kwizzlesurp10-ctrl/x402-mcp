import { describe, expect, it } from "vitest";
import { backoffMs, shouldReconnect, STATS_POLL_MS } from "./sseReconnect";

describe("shouldReconnect", () => {
  it("reconnects only when enabled and polling", () => {
    expect(shouldReconnect("polling", true)).toBe(true);
    expect(shouldReconnect("polling", false)).toBe(false);
    expect(shouldReconnect("live", true)).toBe(false);
    expect(shouldReconnect("dead", true)).toBe(false);
  });
});

describe("backoffMs", () => {
  it("grows exponentially and caps", () => {
    expect(backoffMs(0)).toBe(2_000);
    expect(backoffMs(1)).toBe(4_000);
    expect(backoffMs(10)).toBe(30_000);
  });
});

describe("stats poll interval", () => {
  it("keeps 10s polling fallback contract", () => {
    expect(STATS_POLL_MS).toBe(10_000);
  });
});