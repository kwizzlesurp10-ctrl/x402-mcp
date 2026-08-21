import { describe, it, expect } from "vitest";
import { API, API_BASE } from "./client";

describe("client API_BASE fallback", () => {
  it("resolves to empty string when no VITE variable is set", () => {
    expect(API_BASE).toBe("");
  });

  it("resolves to empty string when no VITE variable is set", () => {
    expect(API).toBe("");
  });
});
