import { describe, expect, it } from "vitest";
import { defaultApiBase, isValidApiBase } from "./config";

describe("config", () => {
  it("accepts dev proxy and http(s) URLs", () => {
    expect(isValidApiBase("/api")).toBe(true);
    expect(isValidApiBase("http://127.0.0.1:8402")).toBe(true);
    expect(isValidApiBase("https://example.com")).toBe(true);
    expect(isValidApiBase("not-a-url")).toBe(false);
  });

  it("defaults to /api in dev mode", () => {
    expect(defaultApiBase()).toBe("/api");
  });
});
