/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ActiveStorefront } from "./ActiveStorefront";
import type { SwarmProduct, LedgerRow } from "../api/client";
import type { StreamEvent } from "../hooks/useSSE";

const mockProducts: SwarmProduct[] = [
  {
    product_id: "prod-alpha-01",
    topic: "Autonomous Research Alpha",
    cost_basis_usdc: 0.05,
    price_usdc: 0.25,
    margin_usdc: 0.2,
    markup: 5,
    network: "Base eip155:8453",
    status: "listed",
    sources: ["https://example.com/source"],
    revenue_usdc: 1.25,
  },
];

const mockRevenueRows: LedgerRow[] = [
  {
    path: "/mn/property-check",
    amount_usdc: 0.85,
  },
  {
    product_id: "mn-property-check",
    amount_usdc: 0.85,
  },
  {
    product_id: "prod-alpha-01",
    amount_usdc: 0.25,
  },
];

const mockActivityEvents: StreamEvent[] = [
  {
    ts: new Date().toISOString(),
    tool: "mn_property_diligence",
    agent_id: "scout-01",
    meta: { path: "/mn/property-check" },
  },
  {
    ts: new Date().toISOString(),
    tool: "prod-alpha-01",
    agent_id: "buyer-02",
    meta: { run_id: "prod-alpha-01" },
  },
];

describe("ActiveStorefront Component", () => {
  afterEach(() => cleanup());

  it("renders MARC-HD Compliance Verification with $0.85 USDC price and Base network badge", () => {
    render(<ActiveStorefront products={[]} />);

    expect(screen.getByText("MARC-HD Compliance Verification")).toBeDefined();
    expect(screen.getByText("$0.85")).toBeDefined();

    const networkBadges = screen.getAllByText(/Network: Base eip155:8453/i);
    expect(networkBadges.length).toBeGreaterThan(0);
  });

  it("renders habitability compliance indicators for MARC-HD", () => {
    render(<ActiveStorefront products={[]} />);

    expect(screen.getByText("✓ Habitability Score (0-100)")).toBeDefined();
    expect(screen.getByText("✓ License Tier Diligence (T1-T3)")).toBeDefined();
    expect(screen.getByText("✓ 4-Class Verdict Engine")).toBeDefined();
    expect(screen.getByText("✓ ArcGIS REST Parity")).toBeDefined();
  });

  it("dynamically aggregates telemetry incorporating revenueRows and activityEvents", () => {
    render(
      <ActiveStorefront
        products={mockProducts}
        revenueRows={mockRevenueRows}
        activityEvents={mockActivityEvents}
      />
    );

    // Initial base views was 7706, plus 1 mn activityEvent = 7707
    expect(screen.getByText("👁️ 7707 challenges")).toBeDefined();

    // Initial base sales was 14, plus 2 mn revenueRows = 16
    expect(screen.getByText("💰 16 settled")).toBeDefined();
  });

  it("filters calls by category when category filter tabs are clicked", () => {
    render(<ActiveStorefront products={mockProducts} />);

    // Click 'Swarm Composite'
    const swarmFilterBtn = screen.getByRole("button", { name: /^Swarm Composite/i });
    fireEvent.click(swarmFilterBtn);

    // MARC-HD is Canonical Data, so it should not be visible when filtering Swarm Composite
    expect(screen.queryByText("MARC-HD Compliance Verification")).toBeNull();
    expect(screen.getByText("Autonomous Research Alpha")).toBeDefined();

    // Click 'Canonical Data'
    const canonicalFilterBtn = screen.getByRole("button", { name: /^Canonical Data/i });
    fireEvent.click(canonicalFilterBtn);

    expect(screen.getByText("MARC-HD Compliance Verification")).toBeDefined();
    expect(screen.queryByText("Autonomous Research Alpha")).toBeNull();

    // Click 'ALL'
    const allFilterBtn = screen.getByRole("button", { name: /^ALL/i });
    fireEvent.click(allFilterBtn);

    expect(screen.getByText("MARC-HD Compliance Verification")).toBeDefined();
    expect(screen.getByText("Autonomous Research Alpha")).toBeDefined();
  });
});
