import { describe, expect, it } from "vitest";
import { basescanUrl, decodePaymentRequiredBase64, truncateHash } from "./decode402";

describe("decodePaymentRequiredBase64", () => {
  it("decodes valid base64 json", () => {
    const payload = { amount: "10000", network: "eip155:84532" };
    const b64 = btoa(JSON.stringify(payload));
    expect(decodePaymentRequiredBase64(b64)).toEqual(payload);
  });
});

describe("truncateHash", () => {
  it("truncates long hashes", () => {
    expect(truncateHash("0x1234567890abcdef")).toMatch(/…/);
  });
});

describe("basescanUrl", () => {
  it("picks sepolia for testnet", () => {
    expect(basescanUrl("eip155:84532", "0xabc")).toContain("sepolia.basescan");
  });
});