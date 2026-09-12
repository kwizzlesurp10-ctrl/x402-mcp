export const API_BASE = import.meta.env.VITE_PUBLIC_API_BASE_URL || "";
export const API = import.meta.env.VITE_PUBLIC_API_BASE_URL || "";

export type StatsResponse = {
  agents: Array<{
    agent_id: string;
    tier: string;
    calls_this_month: number;
    quota_remaining: number;
    quota_warning: boolean;
    rate_limit_remaining: number;
    tool_credits_remaining: number;
  }>;
  config: {
    has_pay_to: boolean;
    has_buyer_key: boolean;
    redis_mode: string;
    network: string;
    free_tier_monthly_quota: number;
    pro_tier_price: string;
    x402_default_network: string;
    has_ownership_proofs?: boolean;
    ownership_proofs_count?: number;
    pay_to_address?: string;
  };
};

export type HealthResponse = {
  status: string;
  service: string;
  x402_facilitator: string;
  x402_facilitator_network: string;
  wallet_configured: boolean;
  stripe_configured: boolean;
  pay_to_configured: boolean;
  ownership_proofs_configured?: boolean;
};

export type DoctorCheck = {
  id: string;
  name: string;
  status: "pass" | "fail" | "warn" | "skip";
  message: string;
  fix?: string;
};

export type LedgerRow = Record<string, unknown>;

export type CityCatalogItem = {
  code: string;
  name: string;
  state: string;
  service_name: string;
  price: string;
  network: string;
  paid_url: string;
  sample_url: string;
  sample_address: string;
  sources_label: string;
  tags: string[];
  canonical_alias: string | null;
};

export type CityCatalog = {
  network: string;
  price: string;
  network_caip2?: string;
  cities: CityCatalogItem[];
};

export type DemandResource = {
  resource: string;
  challenges_served: number;
  qualified_views: number;
  sales_settled: number;
  sales_in_window: number;
  sales_external: number;
  sales_operator: number;
  sales_unknown: number;
  revenue_usdc?: number;
};

export type DemandReport = {
  resources: DemandResource[];
  total_challenges_served?: number;
  total_qualified_views?: number;
  total_sales_external?: number;
  total_sales_operator?: number;
};

export type SwarmProduct = {
  product_id: string;
  topic: string;
  cost_basis_usdc: number;
  price_usdc: number;
  margin_usdc: number;
  markup: number;
  network: string;
  status: string;
  sources: string[];
  revenue_usdc: number;
};

export type SwarmStorefrontRevenue = {
  revenue_usdc: number;
  settled_sales: number;
  external_usdc: number;
  operator_usdc: number;
  unknown_usdc: number;
  external_sales: number;
  operator_sales: number;
  unknown_sales: number;
  first_party_revenue_usdc: number;
  swarm_revenue_usdc: number;
};

export type SwarmProfitRoute = {
  id: string;
  name: string;
  priority_score: number;
  raw_score: number;
  blocked_by: string[];
  human_gated: boolean;
  status_note: string;
  next_action: string;
};

export type SwarmBacklogItem = {
  charter: string;
  title: string;
  status: string;
  human_gated: boolean;
  detail: string;
};

export type SwarmAssessment = {
  generated_at: string;
  signals: Record<string, unknown>;
  profit_routes: SwarmProfitRoute[];
  recommended_route: {
    id: string;
    name: string;
    priority_score: number;
    why: string;
    next_action: string;
  };
  backlog: SwarmBacklogItem[];
  immediate_technical_actions: Array<{ charter: string; title: string; detail: string }>;
  human_gates: string[];
  scoring_model: { weights: Record<string, number>; note: string };
};

export type SwarmRevenue = {
  scope?: "swarm_composites";
  note?: string;
  total_spend_usdc: number; total_revenue_usdc: number; realized_margin_usdc: number;
  ltv_cac: number | null; target_ltv_cac: number;
  listed_count: number; listed_unsold_count?: number; sold_count: number;
  products: Array<{
    product_id: string; topic: string; cost_basis_usdc: number; price_usdc: number;
    margin_usdc: number; status: string; ltv_cac_projected: number;
    revenue_usdc?: number; sales_settled?: number;
  }>;
  source_scores: Array<{ source: string; buys: number; spend_usdc: number; revenue_usdc: number; profit_score: number }>;
  recommendations: string[];
  storefront?: SwarmStorefrontRevenue;
};

export type PulseResponse = {
  generated_at: string;
  chain: { name: string; network: string };
  latest_block: number;
  eth_price_usd: number;
  network: { block_time_s: number; tps_est: number; gas_limit: number; gas_target: number };
  fees: {
    base_fee_gwei: number;
    priority_fee_gwei: number;
    next_base_fee_gwei: number;
    next_base_fee_change_pct: number;
  };
  utilization: {
    now_pct: number;
    avg_pct: number;
    trend: "rising" | "falling" | "flat";
    headroom_x: number;
    series_pct: number[];
  };
  settlement_cost: {
    eth_transfer: { usd: number };
    erc20_usdc_transfer: { usd: number };
    x402_settle: { usd: number };
  };
  assessment: {
    congestion: string;
    verdict: "SETTLE_NOW" | "SETTLE_SOON" | "HOLD_IF_FLEXIBLE";
    rationale: string;
    window: string;
  };
};

export type OsSnapshot = {
  ts: string;
  status: "ok" | "warn" | "critical";
  concerns: string[];
  cpu: {
    percent: number;
    cores_logical: number | null;
    cores_physical: number | null;
    load_avg: number[] | null;
  };
  memory: { total_mb: number; available_mb: number; percent: number };
  swap: { total_mb: number; used_mb: number; percent: number };
  disk: { path: string; total_gb: number; free_gb: number; percent: number };
  network: {
    bytes_sent: number;
    bytes_recv: number;
    sent_kbps: number | null;
    recv_kbps: number | null;
  } | null;
  process: { pid: number; rss_mb: number; cpu_percent: number; threads: number } | null;
  system: { platform: string; python: string; process_count: number; uptime_seconds: number };
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export type WalletResponse = {
  receive_address: string | null;
  vault_address: string | null;
  balances: {
    sepolia_usdc_atomic: number | null;
    mainnet_usdc_atomic: number | null;
  };
  faucet_url: string;
  network: string;
  note: string;
};

export type TelemetryResponse = {
  total_volume_usdc: number;
  total_transactions: number;
  facilitators: Array<{
    id: string;
    name: string;
    url: string;
    uptime: string;
    avgLatencyMs: number;
    supportedSchemes: string[];
    chains: string[];
    status: "active" | "degraded" | "syncing";
  }>;
  uptime_pct: number;
};

export const api = {
  health: () => getJson<HealthResponse>("/health"),
  stats: () => getJson<StatsResponse>("/stats"),
  doctor: () => getJson<{ checks: DoctorCheck[]; summary: { ready: boolean; fail?: number } }>("/doctor"),
  ledgerSpend: () => getJson<LedgerRow[]>("/ledger/spend"),
  ledgerRevenue: () => getJson<LedgerRow[]>("/ledger/revenue"),
  wallet: () => getJson<WalletResponse>("/wallet"),
  pulse: () => getJson<PulseResponse>("/pulse"),
  os: () => getJson<OsSnapshot>("/os"),
  swarmProducts: () => getJson<SwarmProduct[]>("/swarm/products"),
  swarmRevenue: () => getJson<SwarmRevenue>("/swarm/revenue"),
  swarmAssessment: () => getJson<SwarmAssessment>("/swarm/assessment"),
  telemetry: () => getJson<TelemetryResponse>("/telemetry"),
  usCities: () => getJson<CityCatalog>("/us/cities"),
  demand: () => getJson<DemandReport>("/demand"),
  probe: (url: string, method = "GET") =>
    getJson<Record<string, unknown>>(
      `/probe?url=${encodeURIComponent(url)}&method=${encodeURIComponent(method)}`,
    ),
  sellerRequirements: (body: {
    network: string;
    price: string;
    description: string;
    pay_to?: string;
    scheme?: string;
  }) =>
    fetch(`${API}/seller/requirements`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(async (res) => {
      if (!res.ok) throw new Error(await res.text());
      return res.json() as Promise<Record<string, unknown>>;
    }),
};