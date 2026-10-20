/** Single glossary powering all tooltips and "what am I looking at" explainers. */

export const glossary: Record<string, { short: string; long: string }> = {
  "402": {
    short: "HTTP status code meaning payment required",
    long: "A server returns HTTP 402 when it requires payment before granting access. x402 standardizes this with PAYMENT-REQUIRED and PAYMENT-SIGNATURE headers.",
  },
  facilitator: {
    short: "Settlement service that verifies and settles on-chain payments",
    long: "The x402 facilitator validates payment signatures and settles USDC transfers on-chain. It ensures both buyer and seller can trust the payment without direct interaction.",
  },
  settle: {
    short: "Finalize a payment on-chain",
    long: "Settlement is when the facilitator moves USDC from the buyer's wallet to the seller's wallet on the blockchain. Until settled, a payment is just a signed intent.",
  },
  atomicUnits: {
    short: "USDC amounts in smallest unit (1 USDC = 1,000,000 atomic)",
    long: "Like cents to dollars, atomic units prevent floating-point errors in money math. $0.01 = 10,000 atomic units. All calculations use atomic; display converts to human-readable.",
  },
  quota: {
    short: "Monthly limit on MCP tool calls",
    long: "Each agent gets a monthly call quota (500 free, 50k pro). This prevents runaway costs and ensures fair usage. Resets on the first of each month.",
  },
  metaEnvelope: {
    short: "Commerce metadata attached to every MCP tool response",
    long: "Every tool response wraps data in {data, meta}. Meta includes quota remaining, tier, rate limits, and upgrade URLs so agents can self-manage their usage.",
  },
  rateLimit: {
    short: "Maximum tool calls per minute",
    long: "Rate limiting prevents burst abuse. Free tier: 10/min, Pro: 120/min. When exceeded, the server returns a retry-after duration.",
  },
  probe: {
    short: "Check a URL for x402 payment requirements without paying",
    long: "Probing sends a request and reads the 402 response headers. No wallet needed. Useful for discovering what a paid service costs before committing.",
  },
  bazaar: {
    short: "x402 service directory for discovering paid APIs",
    long: "The CDP Bazaar lists HTTP services that accept x402 micropayments. Agents can browse by price, keyword, or network to find services.",
  },
  network: {
    short: "Blockchain network for payments (e.g., Base Mainnet, Sepolia)",
    long: "x402 supports multiple networks identified by CAIP-2 IDs. Base Sepolia (eip155:84532) is the testnet. Base Mainnet (eip155:8453) uses real USDC.",
  },
};

export function getTooltip(term: string): string | undefined {
  return glossary[term]?.short;
}
