import { parseUsdcToAtomic } from "./usdc";
import type { CityCatalogItem, DemandReport, DemandResource, SwarmProduct, LedgerRow } from "../api/client";

export type StorefrontCategory = "Canonical Data" | "US Compliance Network" | "Swarm Composite";

export type ActiveCall = {
  id: string;
  name: string;
  path: string;
  samplePath: string | null;
  priceUsdc: number;
  costBasisUsdc: number;
  category: StorefrontCategory;
  views: number;
  qualifiedViews: number;
  sales: number;
  operatorSettles: number;
  status: "LIVE FOR SALE" | "SOLD";
};

const EMPTY_DEMAND: DemandResource = {
  resource: "",
  challenges_served: 0,
  qualified_views: 0,
  sales_settled: 0,
  sales_in_window: 0,
  sales_external: 0,
  sales_operator: 0,
  sales_unknown: 0,
};

export function pathFromUrl(url: string | null | undefined, fallback = "/"): string {
  if (!url) return fallback;
  try {
    const parsed = new URL(url, "https://x402-mcp.onrender.com");
    return parsed.pathname || fallback;
  } catch {
    return url.startsWith("/") ? url : `/${url}`;
  }
}

export function parsePriceUsdc(price: string | number | null | undefined): number {
  if (typeof price === "number" && Number.isFinite(price)) return price;
  if (typeof price !== "string") return 0;
  const atomic = parseUsdcToAtomic(price);
  return atomic == null ? 0 : atomic / 1_000_000;
}

export function indexDemand(report: DemandReport | null | undefined): Map<string, DemandResource> {
  const map = new Map<string, DemandResource>();
  for (const row of report?.resources ?? []) {
    if (row?.resource) map.set(row.resource, row);
  }
  return map;
}

function addDemand(a: DemandResource, b: DemandResource | undefined): DemandResource {
  if (!b) return a;
  return {
    resource: a.resource || b.resource,
    challenges_served: a.challenges_served + b.challenges_served,
    qualified_views: a.qualified_views + b.qualified_views,
    sales_settled: a.sales_settled + b.sales_settled,
    sales_in_window: a.sales_in_window + b.sales_in_window,
    sales_external: a.sales_external + b.sales_external,
    sales_operator: a.sales_operator + b.sales_operator,
    sales_unknown: a.sales_unknown + b.sales_unknown,
    revenue_usdc: (a.revenue_usdc ?? 0) + (b.revenue_usdc ?? 0),
  };
}

/** Minneapolis is sold on both /mn/property-check and /us/mn/property-check. */
export function demandForCity(index: Map<string, DemandResource>, code: string): DemandResource {
  const network = index.get(`us-city-${code}-property-check`);
  if (code === "mn") {
    return addDemand(
      addDemand({ ...EMPTY_DEMAND, resource: "mn-property-check" }, index.get("mn-property-check")),
      network,
    );
  }
  return network ?? { ...EMPTY_DEMAND, resource: `us-city-${code}-property-check` };
}

export function buildCityCalls(
  cities: CityCatalogItem[] | null | undefined,
  demand: DemandReport | null | undefined,
): ActiveCall[] {
  const index = indexDemand(demand);
  return (cities ?? []).map((city) => {
    const stats = demandForCity(index, city.code);
    const path = city.canonical_alias || pathFromUrl(city.paid_url, `/us/${city.code}/property-check`);
    return {
      id: `city-${city.code}`,
      name: city.service_name || `${city.name}, ${city.state}`,
      path,
      samplePath: pathFromUrl(city.sample_url, `/us/${city.code}/property-check/sample`),
      priceUsdc: parsePriceUsdc(city.price),
      costBasisUsdc: 0,
      category: city.canonical_alias ? "Canonical Data" : "US Compliance Network",
      views: stats.challenges_served,
      qualifiedViews: stats.qualified_views,
      sales: stats.sales_external,
      operatorSettles: stats.sales_operator,
      status: "LIVE FOR SALE",
    };
  });
}

export function buildSwarmCalls(
  products: SwarmProduct[] | null | undefined,
  revenueRows: LedgerRow[] | null | undefined,
  demand: DemandReport | null | undefined,
): ActiveCall[] {
  const index = indexDemand(demand);
  const rows = revenueRows ?? [];
  return (products ?? []).map((p) => {
    const stats = index.get(p.product_id);
    const matchingSales = rows.filter(
      (r) => String(r.product_id || "") === p.product_id,
    ).length;
    return {
      id: p.product_id,
      name: p.topic || `Swarm Product ${p.product_id.slice(0, 8)}`,
      path: `/swarm/products/${p.product_id}/purchase`,
      samplePath: null,
      priceUsdc: p.price_usdc,
      costBasisUsdc: p.cost_basis_usdc,
      category: "Swarm Composite",
      views: stats?.challenges_served ?? 0,
      qualifiedViews: stats?.qualified_views ?? 0,
      sales: stats?.sales_external ?? 0,
      operatorSettles: stats?.sales_operator ?? matchingSales,
      status: p.status === "sold" ? "SOLD" : "LIVE FOR SALE",
    };
  });
}

export function buildStorefrontCalls(opts: {
  cities?: CityCatalogItem[] | null;
  demand?: DemandReport | null;
  products?: SwarmProduct[] | null;
  revenueRows?: LedgerRow[] | null;
}): ActiveCall[] {
  return [
    ...buildCityCalls(opts.cities, opts.demand),
    ...buildSwarmCalls(opts.products, opts.revenueRows, opts.demand),
  ];
}
