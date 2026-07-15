import { describe, expect, it } from "vitest";
import { deriveMissionSteps } from "./mission";

describe("deriveMissionSteps", () => {
  it("marks server and net from live data", () => {
    const steps = deriveMissionSteps({
      stats: { agents: [], config: { has_pay_to: false, has_buyer_key: false, redis_mode: "memory", network: "eip155:84532", free_tier_monthly_quota: 500, pro_tier_price: "$29", x402_default_network: "eip155:84532" } },
      spend: [],
      revenue: [{ amount_usdc_atomic: 50_000 }],
      activity: [],
      apiError: null,
      liveOk: true,
      probeDone: false,
      walletSepoliaAtomic: 0,
      doctor: [],
    });
    expect(steps.find((s) => s.id === "server")?.done).toBe(true);
    expect(steps.find((s) => s.id === "revenue")?.done).toBe(true);
  });
});