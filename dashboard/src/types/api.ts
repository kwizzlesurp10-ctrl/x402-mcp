/** API response types from the FastAPI backend */

export interface AgentStats {
  agent_id: string;
  tier: string;
  calls_this_month: number;
  quota_remaining: number;
  quota_warning: boolean;
  rate_limit_remaining: number;
  tool_credits_remaining: number;
}

export interface ConfigEcho {
  has_pay_to: boolean;
  has_buyer_key: boolean;
  redis_mode: "memory" | "redis";
  network: string;
  free_tier_monthly_quota: number;
  free_tier_rate_limit_per_min: number;
  pro_tier_monthly_quota: number;
  pro_tier_rate_limit_per_min: number;
  pro_tier_price: string;
  tool_credit_pack_size: number;
  tool_credit_pack_price: string;
  x402_default_network: string;
  x402_default_price: string;
  dashboard_actions: boolean;
}

export interface StatsResponse {
  agents: AgentStats[];
  config: ConfigEcho;
}

export interface DoctorCheck {
  id: string;
  label: string;
  passed: boolean;
  fix: string;
  detail: string;
}

export interface DoctorResponse {
  ok: boolean;
  checks: DoctorCheck[];
}

export interface ToolEvent {
  ts: string;
  tool: string;
  agent_id: string;
  meta: Record<string, unknown>;
  type?: "heartbeat";
}

export interface LedgerRow {
  ts: string;
  amount_usdc?: number;
  amount_atomic?: number;
  network?: string;
  tx_hash?: string;
  agent_id?: string;
  tool?: string;
  status?: string;
  [key: string]: unknown;
}

export interface WalletBalance {
  address: string;
  usdc_atomic: number;
  usdc_human: string;
  funded: boolean;
}

export interface WalletResponse {
  vault_address: string | null;
  pay_to_address: string | null;
  network: string;
  balances: Record<string, WalletBalance>;
}

export interface ProbeResponse {
  url: string;
  method: string;
  status_code: number;
  payment_required: boolean;
  payment_required_header?: string | null;
  payment_required_decoded?: Record<string, unknown> | null;
  payment_required_body?: Record<string, unknown> | null;
}

export type ConnectionStatus = "connected" | "polling" | "disconnected";

export type DensityMode = "guided" | "standard" | "operator";
