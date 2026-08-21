import { describe, it, expect } from "vitest";
import { shouldReconnect, backoffMs, STATS_POLL_MS } from "./sseReconnect";

describe("sseReconnect", () => {
  describe("shouldReconnect", () => {
    it("returns true only when degraded and enabled", () => {
      expect(shouldReconnect("degraded", true)).toBe(true);
      expect(shouldReconnect("degraded", false)).toBe(false);
      expect(shouldReconnect("connected", true)).toBe(false);
      expect(shouldReconnect("checking", true)).toBe(false);
      expect(shouldReconnect("disconnected", true)).toBe(false);
    });
  });

  describe("backoffMs", () => {
    it("exponentially backs off", () => {
      expect(backoffMs(0)).toBe(2000);
      expect(backoffMs(1)).toBe(4000);
      expect(backoffMs(2)).toBe(8000);
      expect(backoffMs(10)).toBe(30000); // capped at 30s
    });
  });
});

describe("stats poll interval", () => {
  it("keeps 10s polling fallback contract", () => {
    expect(STATS_POLL_MS).toBe(10_000);
  });
});