import { describe, expect, it } from "vitest";
import { relativeTime } from "./time";

describe("relativeTime", () => {
  it("formats seconds ago", () => {
    const ts = new Date(Date.now() - 30_000).toISOString();
    expect(relativeTime(ts)).toMatch(/s ago$/);
  });

  it("returns original string for invalid input", () => {
    expect(relativeTime("not-a-date")).toBe("not-a-date");
  });
});