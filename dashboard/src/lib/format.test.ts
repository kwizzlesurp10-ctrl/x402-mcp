import { describe, it, expect } from "vitest";
import {
  formatUsdc,
  formatUsdcHuman,
  priceToAtomic,
  truncateHash,
  baseScanUrl,
  networkLabel,
  networkColor,
} from "./format";

describe("formatUsdc", () => {
  it("formats zero", () => {
    expect(formatUsdc(0)).toBe("$0.00");
  });

  it("formats small amounts with 6 decimals", () => {
    expect(formatUsdc(1)).toBe("$0.000001");
  });

  it("formats 10000 atomic to $0.01", () => {
    expect(formatUsdc(10000)).toBe("$0.01");
  });

  it("formats 1000000 atomic to $1.00", () => {
    expect(formatUsdc(1000000)).toBe("$1.00");
  });

  it("formats 29000000 atomic to $29.00", () => {
    expect(formatUsdc(29000000)).toBe("$29.00");
  });

  it("handles negative amounts", () => {
    expect(formatUsdc(-10000)).toBe("$-0.01");
  });
});

describe("formatUsdcHuman", () => {
  it("formats 0.01 human to $0.01", () => {
    expect(formatUsdcHuman(0.01)).toBe("$0.01");
  });

  it("formats 0 to $0.00", () => {
    expect(formatUsdcHuman(0)).toBe("$0.00");
  });
});

describe("priceToAtomic", () => {
  it("converts $0.01 to 10000", () => {
    expect(priceToAtomic("$0.01")).toBe(10000);
  });

  it("converts $29.00 to 29000000", () => {
    expect(priceToAtomic("$29.00")).toBe(29000000);
  });

  it("converts $1.00 to 1000000", () => {
    expect(priceToAtomic("$1.00")).toBe(1000000);
  });
});

describe("truncateHash", () => {
  it("truncates long hashes", () => {
    const hash = "0x1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b";
    const result = truncateHash(hash);
    expect(result).toBe("0x1a2b…9a0b");
  });

  it("returns short strings unchanged", () => {
    expect(truncateHash("0x1234")).toBe("0x1234");
  });
});

describe("baseScanUrl", () => {
  it("returns sepolia URL for testnet", () => {
    const url = baseScanUrl("0xabc", "eip155:84532");
    expect(url).toBe("https://sepolia.basescan.org/tx/0xabc");
  });

  it("returns mainnet URL for mainnet", () => {
    const url = baseScanUrl("0xabc", "eip155:8453");
    expect(url).toBe("https://basescan.org/tx/0xabc");
  });
});

describe("networkLabel", () => {
  it("identifies Base Mainnet", () => {
    expect(networkLabel("eip155:8453")).toBe("Base Mainnet");
  });

  it("identifies Base Sepolia", () => {
    expect(networkLabel("eip155:84532")).toBe("Base Sepolia");
  });

  it("returns raw for unknown", () => {
    expect(networkLabel("eip155:1")).toBe("eip155:1");
  });
});

describe("networkColor", () => {
  it("returns blue for mainnet", () => {
    expect(networkColor("eip155:8453")).toBe("#0052FF");
  });

  it("returns amber for testnet", () => {
    expect(networkColor("eip155:84532")).toBe("#F5A623");
  });
});
