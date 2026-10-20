/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BazaarResourceExplorer } from "./BazaarResourceExplorer";
import * as client from "../api/client";
import { PINNED_PULSE_PRODUCT_ID } from "../utils/storefront";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      usCities: vi.fn(),
      demand: vi.fn(),
      probe: vi.fn(),
    },
  };
});

describe("BazaarResourceExplorer", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("lists only live storefront resources and includes pinned Pulse path", async () => {
    vi.mocked(client.api.usCities).mockResolvedValue({
      network: "eip155:8453",
      price: "$0.01",
      cities: [
        {
          code: "sea",
          name: "Seattle",
          state: "WA",
          service_name: "Seattle Rental Compliance",
          price: "$0.01",
          network: "eip155:8453",
          paid_url: "https://x402-mcp.onrender.com/us/sea/property-check",
          sample_url: "https://x402-mcp.onrender.com/us/sea/property-check/sample",
          sample_address: "1531 BELMONT AVE",
          sources_label: "Seattle open data",
          tags: [],
          canonical_alias: null,
        },
      ],
    });
    vi.mocked(client.api.demand).mockResolvedValue({ resources: [] });

    render(
      <BazaarResourceExplorer
        density="standard"
        products={[
          {
            product_id: PINNED_PULSE_PRODUCT_ID,
            topic: "Base Network Pulse",
            cost_basis_usdc: 0,
            price_usdc: 0.05,
            margin_usdc: 0.05,
            markup: 0,
            network: "eip155:8453",
            status: "listed",
            sources: [],
            revenue_usdc: 0.45,
          },
        ]}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Seattle Rental Compliance/i)).toBeDefined();
    });

    expect(screen.queryByText(/Llama-3.3/i)).toBeNull();
    expect(screen.queryByText(/Stealth Web Scraper/i)).toBeNull();
    expect(
      screen.getByText(`/swarm/products/${PINNED_PULSE_PRODUCT_ID}/purchase`),
    ).toBeDefined();
    expect(screen.getByText("$0.05 USDC")).toBeDefined();
  });
});
