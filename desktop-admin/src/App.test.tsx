import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { StreamEvent } from "./hooks/useSSE";

vi.mock("@dashboard/components/ActiveStorefront", () => ({ ActiveStorefront: () => null }));
vi.mock("@dashboard/components/OsHealthPanel", () => ({ OsHealthPanel: () => null }));
vi.mock("@dashboard/components/PulsePanel", () => ({ PulsePanel: () => null }));
vi.mock("@dashboard/components/SwarmActivity", () => ({ SwarmActivity: () => null }));
vi.mock("@dashboard/components/SwarmAssessmentPanel", () => ({
  SwarmAssessmentPanel: () => <div>Strategic assessment</div>,
}));
vi.mock("@dashboard/components/VirtualizedLedger", () => ({ VirtualizedLedger: () => null }));
vi.mock("@dashboard/components/Inspector402", () => ({ Inspector402: () => null }));
vi.mock("@dashboard/components/WalletPanel", () => ({ WalletPanel: () => null }));
vi.mock("@dashboard/components/RateSparkline", () => ({ RateSparkline: () => null }));
vi.mock("@dashboard/components/CommandPalette", () => ({ CommandPalette: () => null }));
vi.mock("@dashboard/components/SellerWizard", () => ({ SellerWizard: () => null }));
vi.mock("./components/MailRailPanel", () => ({
  MailRailPanel: () => <div>AgentMail / MailRail</div>,
}));

const mockDoctor = vi.fn().mockResolvedValue({ checks: [], summary: { ready: true } });
let sseOnEvent: ((e: StreamEvent) => void) | null = null;

vi.mock("./api/client", () => ({
  getApiBase: () => "/api",
  setApiBase: vi.fn(),
  api: {
    stats: vi.fn().mockResolvedValue({
      agents: [],
      config: { free_tier_monthly_quota: 500 },
    }),
    doctor: (...args: unknown[]) => mockDoctor(...args),
    ledgerSpend: vi.fn().mockResolvedValue([]),
    ledgerRevenue: vi.fn().mockResolvedValue([]),
    wallet: vi.fn().mockResolvedValue({
      receive_address: null,
      vault_address: null,
      balances: { sepolia_usdc_atomic: null, mainnet_usdc_atomic: null },
      faucet_url: "",
      network: "eip155:84532",
      note: "",
    }),
    swarmProducts: vi.fn().mockResolvedValue([]),
    swarmRevenue: vi.fn().mockResolvedValue({
      total_spend_usdc: 0,
      total_revenue_usdc: 0,
      realized_margin_usdc: 0,
      ltv_cac: null,
      target_ltv_cac: 3,
      listed_count: 0,
      sold_count: 0,
      products: [],
      source_scores: [],
      recommendations: [],
    }),
    swarmAssessment: vi.fn().mockResolvedValue(null),
    pulse: vi.fn().mockResolvedValue(null),
    os: vi.fn().mockResolvedValue(null),
    mailrailHealth: vi.fn(),
    mailrailLedger: vi.fn(),
    mailrailInbox: vi.fn(),
    mailrailStats: vi.fn(),
  },
}));

vi.mock("./hooks/useSSE", () => ({
  useSSE: (_enabled: boolean, onEvent: (e: StreamEvent) => void) => {
    sseOnEvent = onEvent;
    return { status: "connected", reconnect: vi.fn() };
  },
}));

import App from "./App";

describe("Admin App", () => {
  it("renders admin header and operator panels", async () => {
    render(<App />);
    expect(screen.getByText("// admin")).toBeInTheDocument();
    expect(await screen.findByText("Net position")).toBeInTheDocument();
    expect(screen.getByText("AgentMail / MailRail")).toBeInTheDocument();
  });

  it("auto-opens doctor modal once on initial load, not on SSE refresh", async () => {
    mockDoctor.mockResolvedValue({
      checks: [{ id: "wallet", name: "Wallet", status: "fail", message: "Missing key" }],
      summary: { ready: false },
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: "Doctor checks" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Doctor checks" })).not.toBeInTheDocument();

    sseOnEvent?.({ ts: "2026-09-12T00:00:00Z", tool: "stats" });

    await waitFor(() => {
      expect(mockDoctor.mock.calls.length).toBeGreaterThan(1);
    });
    expect(screen.queryByRole("dialog", { name: "Doctor checks" })).not.toBeInTheDocument();
  });
});
