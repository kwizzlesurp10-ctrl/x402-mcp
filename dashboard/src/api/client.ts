const API = "/api";

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
  };
};

export type DoctorCheck = {
  id: string;
  name: string;
  status: "pass" | "fail" | "warn" | "skip";
  message: string;
  fix?: string;
};

export type LedgerRow = Record<string, unknown>;

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

export type SwarmRevenue = {
  total_spend_usdc: number; total_revenue_usdc: number; realized_margin_usdc: number;
  ltv_cac: number | null; target_ltv_cac: number;
  listed_count: number; sold_count: number;
  products: Array<{ product_id: string; topic: string; cost_basis_usdc: number; price_usdc: number; margin_usdc: number; status: string; ltv_cac_projected: number }>;
  source_scores: Array<{ source: string; buys: number; spend_usdc: number; revenue_usdc: number; profit_score: number }>;
  recommendations: string[];
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

export const api = {
  stats: () => getJson<StatsResponse>("/stats"),
  doctor: () => getJson<{ checks: DoctorCheck[]; summary: { ready: boolean; fail?: number } }>("/doctor"),
  ledgerSpend: () => getJson<LedgerRow[]>("/ledger/spend"),
  ledgerRevenue: () => getJson<LedgerRow[]>("/ledger/revenue"),
  wallet: () => getJson<WalletResponse>("/wallet"),
  swarmProducts: () => getJson<SwarmProduct[]>("/swarm/products"),
  swarmRevenue: () => getJson<SwarmRevenue>("/swarm/revenue"),
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