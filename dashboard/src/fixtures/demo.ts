import type { DoctorCheck, LedgerRow, OsSnapshot, StatsResponse } from "../api/client";

export const demoStats: StatsResponse = {
  agents: [
    { agent_id: "scout-01", tier: "free", calls_this_month: 42, quota_remaining: 458, quota_warning: false, rate_limit_remaining: 7, tool_credits_remaining: 0 },
    { agent_id: "treasurer-01", tier: "free", calls_this_month: 8, quota_remaining: 492, quota_warning: false, rate_limit_remaining: 9, tool_credits_remaining: 0 },
    { agent_id: "merchant-01", tier: "pro", calls_this_month: 120, quota_remaining: 49880, quota_warning: false, rate_limit_remaining: 110, tool_credits_remaining: 50 },
  ],
  config: {
    has_pay_to: true,
    has_buyer_key: true,
    redis_mode: "memory",
    network: "eip155:84532",
    free_tier_monthly_quota: 500,
    pro_tier_price: "$29.00",
    x402_default_network: "eip155:84532",
  },
};

export const demoSpend: LedgerRow[] = [
  {
    ts: "2026-07-09T12:00:00Z",
    url: "https://api.example/paid",
    network: "eip155:84532",
    amount_usdc_atomic: 0,
    testnet: true,
    nominal_usdc_atomic: 10_000,
    tx: "0xabc123def4567890",
    settle_ok: true,
    agent_id: "treasurer-01",
  },
];

export const demoRevenue: LedgerRow[] = [
  {
    ts: "2026-07-09T13:00:00Z",
    amount_usdc_atomic: 290_000,
    network: "eip155:84532",
    payer: "0xBuyer",
    resource: "pro-upgrade",
    verified: true,
  },
];

export const demoActivity = [
  { type: "tool", ts: "2026-07-09T13:05:00Z", tool: "discover_services", agent_id: "scout-01", meta: { quota_remaining: 458 } },
  { type: "tool", ts: "2026-07-09T13:04:00Z", tool: "get_payment_requirements", agent_id: "scout-01", meta: { quota_remaining: 459 } },
  { type: "tool", ts: "2026-07-09T13:03:00Z", tool: "pay_and_fetch", agent_id: "treasurer-01", meta: { quota_remaining: 492 } },
];

export const demoOs: OsSnapshot = {
  ts: "2026-07-09T13:05:00Z",
  status: "warn",
  concerns: ["memory at 86.4% (warn)"],
  cpu: { percent: 22.5, cores_logical: 12, cores_physical: 6, load_avg: null },
  memory: { total_mb: 7488.0, available_mb: 1019.6, percent: 86.4 },
  swap: { total_mb: 12160.0, used_mb: 3480.2, percent: 28.6 },
  disk: { path: "C:\\", total_gb: 930.57, free_gb: 320.4, percent: 65.6 },
  network: { bytes_sent: 1_204_000, bytes_recv: 9_811_000, sent_kbps: 4.2, recv_kbps: 38.7 },
  process: { pid: 4242, rss_mb: 96.3, cpu_percent: 1.2, threads: 14 },
  system: {
    platform: "Windows-11 (demo)",
    python: "3.12.0",
    process_count: 284,
    uptime_seconds: 2 * 86400 + 5 * 3600,
  },
};

export const demoDoctor: DoctorCheck[] = [
  { id: "pay_to", name: "Receive wallet", status: "pass", message: "Configured (demo)" },
  { id: "buyer_key", name: "Vault key", status: "pass", message: "Configured (demo)" },
  { id: "facilitator", name: "Facilitator", status: "pass", message: "Reachable (demo)" },
];