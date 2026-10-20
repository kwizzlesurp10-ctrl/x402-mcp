import { describe, it, expect } from "vitest";
import { glossary, getTooltip } from "./glossary";

describe("glossary", () => {
  it("has entries for core x402 terms", () => {
    expect(glossary["402"]).toBeDefined();
    expect(glossary.facilitator).toBeDefined();
    expect(glossary.settle).toBeDefined();
    expect(glossary.atomicUnits).toBeDefined();
    expect(glossary.quota).toBeDefined();
  });

  it("each entry has short and long descriptions", () => {
    for (const [key, entry] of Object.entries(glossary)) {
      expect(entry.short, `${key} missing short`).toBeTruthy();
      expect(entry.long, `${key} missing long`).toBeTruthy();
    }
  });
});

describe("getTooltip", () => {
  it("returns short description for known term", () => {
    expect(getTooltip("402")).toBe(glossary["402"].short);
  });

  it("returns undefined for unknown term", () => {
    expect(getTooltip("nonexistent")).toBeUndefined();
  });
});
