export const glossary: Record<string, string> = {
  "402": "HTTP status meaning Payment Required. The server wants USDC before returning data.",
  facilitator: "Service that verifies and settles x402 payments on-chain.",
  quota: "Monthly MCP tool call budget for your agent identity.",
  "meta envelope": "Commerce fields attached to every MCP tool response (tier, quota_remaining, agent_id).",
  "atomic units": "USDC stored as integers with 6 decimal places (1 USDC = 1,000,000 atomic).",
  settle: "On-chain confirmation that a payment was accepted by the seller.",
  probe: "HTTP request that reads PAYMENT-REQUIRED headers without spending funds.",
  net: "Revenue minus mainnet spend from your ledgers. Goal is net ≥ 0.",
};

export function explain(term: string): string {
  return glossary[term] ?? `No glossary entry for ${term}.`;
}