/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ActiveStorefront } from "./ActiveStorefront";
import type { SwarmProduct, LedgerRow } from "../api/client";
import { demoCities, demoDemand } from "../fixtures/demo";

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
    amount_usdc: 0.01,
  },
  {
    product_id: "prod-alpha-01",
    amount_usdc: 0.25,
  },
];

describe("ActiveStorefront Component", () => {
  afterEach(() => cleanup());

  it("renders MN catalog price from /us/cities ($0.01)", () => {
    render(
      <ActiveStorefront
        products={[]}
        demo
        cities={demoCities}
        demand={demoDemand}
      />,
    );

    expect(screen.getByText("MN Rental License Check")).toBeDefined();
    expect(screen.getByText("$0.01")).toBeDefined();
  });

  it("aggregates demand stats from the catalog", () => {
    render(
      <ActiveStorefront
        products={mockProducts}
        revenueRows={mockRevenueRows}
        demo
        cities={demoCities}
        demand={demoDemand}
      />,
    );

    expect(screen.getByText("Autonomous Research Alpha")).toBeDefined();
    expect(screen.getByText("$0.25")).toBeDefined();
  });

  it("filters listings by category", () => {
    render(
      <ActiveStorefront products={mockProducts} demo cities={demoCities} demand={demoDemand} />,
    );

    fireEvent.click(screen.getByText(/Swarm Composite/));
    expect(screen.queryByText("MN Rental License Check")).toBeNull();
    expect(screen.getByText("Autonomous Research Alpha")).toBeDefined();

    fireEvent.click(screen.getByText(/ALL/));
    expect(screen.getByText("MN Rental License Check")).toBeDefined();
  });
});
