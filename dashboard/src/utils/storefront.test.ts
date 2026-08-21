import { describe, expect, it } from "vitest";
import {
  buildCityCalls,
  buildStorefrontCalls,
  demandForCity,
  indexDemand,
  parsePriceUsdc,
  pathFromUrl,
} from "./storefront";
import type { CityCatalogItem, DemandReport } from "../api/client";

const cities: CityCatalogItem[] = [
  {
    code: "mn",
    name: "Minneapolis",
    state: "MN",
    service_name: "MN Rental Compliance",
    price: "$0.01",
    network: "eip155:8453",
    paid_url: "https://x402-mcp.onrender.com/us/mn/property-check",
    sample_url: "https://x402-mcp.onrender.com/us/mn/property-check/sample",
    sample_address: "1700 Penn Ave N",
    sources_label: "Minneapolis open data",
    tags: ["minneapolis"],
    canonical_alias: "/mn/property-check",
  },
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
    tags: ["seattle"],
    canonical_alias: null,
  },
  {
    code: "chi",
    name: "Chicago",
    state: "IL",
    service_name: "Chicago Building Violations",
    price: "$0.01",
    network: "eip155:8453",
    paid_url: "https://x402-mcp.onrender.com/us/chi/property-check",
    sample_url: "https://x402-mcp.onrender.com/us/chi/property-check/sample",
    sample_address: "7840 S WESTERN AVE",
    sources_label: "Chicago open data",
    tags: ["chicago"],
    canonical_alias: null,
  },
];

const demand: DemandReport = {
  resources: [
    {
      resource: "mn-property-check",
      challenges_served: 6709,
      qualified_views: 3486,
      sales_settled: 10,
      sales_in_window: 9,
      sales_external: 0,
      sales_operator: 8,
      sales_unknown: 1,
    },
    {
      resource: "us-city-mn-property-check",
      challenges_served: 997,
      qualified_views: 606,
      sales_settled: 4,
      sales_in_window: 4,
      sales_external: 0,
      sales_operator: 4,
      sales_unknown: 0,
    },
    {
      resource: "us-city-sea-property-check",
      challenges_served: 1284,
      qualified_views: 850,
      sales_settled: 4,
      sales_in_window: 4,
      sales_external: 0,
      sales_operator: 4,
      sales_unknown: 0,
    },
  ],
};

describe("parsePriceUsdc", () => {
  it("parses catalog $0.01 strings", () => {
    expect(parsePriceUsdc("$0.01")).toBe(0.01);
  });
});

describe("pathFromUrl", () => {
  it("keeps the pathname of a public paid_url", () => {
    expect(pathFromUrl("https://x402-mcp.onrender.com/us/sea/property-check")).toBe(
      "/us/sea/property-check",
    );
  });
});

describe("demandForCity", () => {
  it("merges Minneapolis canonical + network keys", () => {
    const row = demandForCity(indexDemand(demand), "mn");
    expect(row.challenges_served).toBe(6709 + 997);
    expect(row.qualified_views).toBe(3486 + 606);
    expect(row.sales_operator).toBe(12);
    expect(row.sales_external).toBe(0);
  });
});

describe("buildCityCalls", () => {
  it("renders every catalog city with live demand, not a hardcoded trio", () => {
    const calls = buildCityCalls(cities, demand);
    expect(calls.map((c) => c.id)).toEqual(["city-mn", "city-sea", "city-chi"]);
    expect(calls[0].path).toBe("/mn/property-check");
    expect(calls[1].path).toBe("/us/sea/property-check");
    expect(calls[2].name).toBe("Chicago Building Violations");
    expect(calls[0].views).toBe(7706);
    expect(calls[0].sales).toBe(0);
    expect(calls[0].operatorSettles).toBe(12);
    expect(calls.some((c) => c.path === "/pulse")).toBe(false);
  });

  it("does not invent views when /demand is missing", () => {
    const calls = buildCityCalls(cities, { resources: [] });
    expect(calls.every((c) => c.views === 0 && c.sales === 0)).toBe(true);
  });
});

describe("buildStorefrontCalls", () => {
  it("lists cities ahead of swarm composites", () => {
    const calls = buildStorefrontCalls({
      cities,
      demand,
      products: [
        {
          product_id: "d22bbf5f3c4b4666a6f80980c7bc7c50",
          topic: "Base Network Pulse @ block 50032697",
          cost_basis_usdc: 0,
          price_usdc: 0.05,
          margin_usdc: 0.05,
          markup: 0,
          network: "eip155:8453",
          status: "listed",
          sources: [],
          revenue_usdc: 0.4,
        },
      ],
    });
    expect(calls).toHaveLength(4);
    expect(calls[3].category).toBe("Swarm Composite");
    expect(calls[3].path).toContain("/swarm/products/");
    expect(calls[3].sales).toBe(0);
  });
});
