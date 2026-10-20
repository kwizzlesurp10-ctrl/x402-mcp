/** Demo mode fixtures — seeded realistic data for screenshot/sales mode. */

import type {
  AgentStats,
  ConfigEcho,
  DoctorCheck,
  LedgerRow,
  StatsResponse,
  ToolEvent,
  WalletResponse,
} from "../types/api";

const now = new Date();
function ago(minutes: number): string {
  return new Date(now.getTime() - minutes * 60_000).toISOString();
}

export const DEMO_CONFIG: ConfigEcho = {
  has_pay_to: true,
  has_buyer_key: true,
  redis_mode: "memory",
  network: "eip155:84532",
  free_tier_monthly_quota: 500,
  free_tier_rate_limit_per_min: 10,
  pro_tier_monthly_quota: 50000,
  pro_tier_rate_limit_per_min: 120,
  pro_tier_price: "$29.00",
  tool_credit_pack_size: 100,
  tool_credit_pack_price: "$1.00",
  x402_default_network: "eip155:84532",
  x402_default_price: "$0.01",
  dashboard_actions: false,
};

export const DEMO_AGENTS: AgentStats[] = [
  {
    agent_id: "scout-01",
    tier: "free",
    calls_this_month: 142,
    quota_remaining: 358,
    quota_warning: false,
    rate_limit_remaining: 8,
    tool_credits_remaining: 0,
  },
  {
    agent_id: "warden-01",
    tier: "free",
    calls_this_month: 89,
    quota_remaining: 411,
    quota_warning: false,
    rate_limit_remaining: 9,
    tool_credits_remaining: 0,
  },
  {
    agent_id: "treasurer-01",
    tier: "pro",
    calls_this_month: 1247,
    quota_remaining: 48753,
    quota_warning: false,
    rate_limit_remaining: 118,
    tool_credits_remaining: 50,
  },
  {
    agent_id: "archivist-01",
    tier: "free",
    calls_this_month: 56,
    quota_remaining: 444,
    quota_warning: false,
    rate_limit_remaining: 10,
    tool_credits_remaining: 0,
  },
  {
    agent_id: "merchant-01",
    tier: "free",
    calls_this_month: 31,
    quota_remaining: 469,
    quota_warning: false,
    rate_limit_remaining: 10,
    tool_credits_remaining: 0,
  },
];

export const DEMO_STATS: StatsResponse = {
  agents: DEMO_AGENTS,
  config: DEMO_CONFIG,
};

const TOOLS = [
  "discover_services",
  "get_payment_requirements",
  "pay_and_fetch",
  "build_seller_requirements",
  "verify_payment_payload",
  "get_supported_networks",
];

const AGENT_IDS = DEMO_AGENTS.map((a) => a.agent_id);

export const DEMO_EVENTS: ToolEvent[] = Array.from({ length: 50 }, (_, i) => ({
  ts: ago(i * 2),
  tool: TOOLS[i % TOOLS.length],
  agent_id: AGENT_IDS[i % AGENT_IDS.length],
  meta: {
    tier: "free",
    quota_remaining: 500 - i,
    rate_limit_remaining: 10 - (i % 5),
  },
}));

export const DEMO_SPEND: LedgerRow[] = [
  {
    ts: ago(5),
    amount_usdc: 0.01,
    amount_atomic: 10000,
    network: "eip155:84532",
    tx_hash: "0x1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b",
    agent_id: "treasurer-01",
    tool: "pay_and_fetch",
    status: "settled",
  },
  {
    ts: ago(12),
    amount_usdc: 0.01,
    amount_atomic: 10000,
    network: "eip155:84532",
    tx_hash: "0x2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c",
    agent_id: "treasurer-01",
    tool: "pay_and_fetch",
    status: "settled",
  },
  {
    ts: ago(30),
    amount_usdc: 0.01,
    amount_atomic: 10000,
    network: "eip155:8453",
    tx_hash: "0x3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d",
    agent_id: "treasurer-01",
    tool: "pay_and_fetch",
    status: "settled",
  },
];

export const DEMO_REVENUE: LedgerRow[] = [
  {
    ts: ago(3),
    amount_usdc: 0.01,
    amount_atomic: 10000,
    network: "eip155:84532",
    tx_hash: "0x4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e",
    agent_id: "buyer-ext-01",
    status: "settled",
  },
  {
    ts: ago(8),
    amount_usdc: 0.01,
    amount_atomic: 10000,
    network: "eip155:84532",
    tx_hash: "0x5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f",
    agent_id: "buyer-ext-02",
    status: "settled",
  },
  {
    ts: ago(15),
    amount_usdc: 29.0,
    amount_atomic: 29000000,
    network: "eip155:84532",
    tx_hash: "0x6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a",
    agent_id: "buyer-ext-01",
    status: "settled",
  },
];

export const DEMO_DOCTOR: DoctorCheck[] = [
  { id: "server_reachable", label: "Server reachable", passed: true, fix: "", detail: "Listening on 0.0.0.0:8402" },
  { id: "pay_to_address", label: "Receive wallet set", passed: true, fix: "", detail: "0xDemo...Address" },
  { id: "buyer_key", label: "Vault key set", passed: true, fix: "", detail: "configured" },
  { id: "facilitator", label: "x402 facilitator reachable", passed: true, fix: "", detail: "HTTP 200" },
  { id: "discovery", label: "CDP discovery reachable", passed: true, fix: "", detail: "HTTP 200" },
  { id: "redis_mode", label: "Store mode", passed: true, fix: "Set REDIS_URL for persistent storage", detail: "memory" },
  { id: "network", label: "Default network", passed: true, fix: "", detail: "eip155:84532" },
];

export const DEMO_WALLET: WalletResponse = {
  vault_address: "0xDemoVault1234567890abcdef1234567890abcdef",
  pay_to_address: "0xDemoPayTo1234567890abcdef1234567890abcdef",
  network: "eip155:84532",
  balances: {
    vault: {
      address: "0xDemoVault1234567890abcdef1234567890abcdef",
      usdc_atomic: 50_000_000,
      usdc_human: "50.000000",
      funded: true,
    },
    pay_to: {
      address: "0xDemoPayTo1234567890abcdef1234567890abcdef",
      usdc_atomic: 29_020_000,
      usdc_human: "29.020000",
      funded: true,
    },
  },
};
