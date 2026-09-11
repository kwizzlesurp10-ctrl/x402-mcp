# TOOL_LEGIBILITY

_Generated 2026-09-11T10:25Z by @veriton-dev for bounty issue #494. Add-only. Live host: `https://x402-mcp.onrender.com`._

Tool names from `app/tools_registry.py` (`TOOL_SPECS`) + live `GET /.well-known/mcp`.
Mark **unknown** instead of inventing atomic amounts when not observed live.

| Tool | Outcome | When to use / when not | Cost visibility | Worked example | Instructive failure |
|---|---|---|---|---|---|
| `x402.agent_card` | Return the A2A Protocol v1.0 Agent ID Card and MCP server card.  Optional target_id filters to a skill id, name, or tag. | USE: Need A2A identity / skill card / NOT: Paid data fetch | free MCP tool tier; may trigger paid HTTP elsewhere | https://x402-mcp.onrender.com/.well-known/agent-card.json | HTTP card 200 at /.well-known/agent-card.json; MCP error shape unknown |
| `x402.discover` | Discover paid HTTP APIs in the x402 Bazaar via the facilitator catalog.  Call this first to find a resource URL, then x402.probe and x402.pay_and_fetch. | USE: Finding bazaar-listed paid APIs / NOT: Already have resource URL | free MCP tool tier; may trigger paid HTTP elsewhere | https://x402-mcp.onrender.com/.well-known/x402 | Facilitator outage → tool error (exact body unknown) |
| `x402.probe` | Probe a URL for HTTP 402 PAYMENT-REQUIRED terms using the x402 client SDK.  Use before x402.pay_and_fetch to inspect price, network, and payTo without spending. | USE: Inspect 402 terms without spending / NOT: Need response body — use pay_and_fetch | free MCP tool tier; may trigger paid HTTP elsewhere | GET https://x402-mcp.onrender.com/us/mn/property-check?address=1700+Penn+Ave+N → HTTP 402 | Live: unpaid property-check → HTTP 402 JSON error=payment_required + payment-required header |
| `x402.pay_and_fetch` | Pay USDC via x402 and fetch a protected HTTP resource in one call.  Requires EVM_PRIVATE_KEY on this host; otherwise use x402.probe for a no-spend 402. | USE: One-shot pay + retrieve protected HTTP / NOT: No EVM_PRIVATE_KEY on host | free MCP tool tier; requires_env=['EVM_PRIVATE_KEY']; may trigger paid HTTP elsewhere | MCP tool; needs EVM_PRIVATE_KEY; pairs with probe URL above | Missing EVM_PRIVATE_KEY → tool refuses spend; bad sig → facilitator reject (body unknown) |
| `x402.build_seller` | Build seller-side x402 payment requirements for your own HTTP resource.  Pass resource_url plus discovery_* fields to catalog the endpoint in Bazaar. | USE: Expose your resource behind x402 / NOT: Buyer-only flows | free MCP tool tier; requires_env=['X402_PAY_TO_ADDRESS']; may trigger paid HTTP elsewhere | MCP tool; needs X402_PAY_TO_ADDRESS | Missing X402_PAY_TO_ADDRESS → cannot build requirements |
| `x402.verify` | Verify an x402 PAYMENT-SIGNATURE against PAYMENT-REQUIRED terms via the facilitator.  Call after a buyer presents a signature and before releasing paid content. | USE: Seller verifying payment signature / NOT: Buyer paying | free MCP tool tier; may trigger paid HTTP elsewhere | MCP tool after buyer PAYMENT-SIGNATURE | Invalid signature → facilitator verification failure (body unknown) |
| `x402.networks` | List supported settlement networks, facilitators, and x402 v2 header names.  Call when choosing a preferred_network for x402.pay_and_fetch or x402.build_seller. | USE: Choose network/facilitator/headers / NOT: Resource URL already pinned | free MCP tool tier; may trigger paid HTTP elsewhere | https://x402-mcp.onrender.com/.well-known/x402 (networks in accepts[]) | unknown |
| `commerce.pro_requirements` | Build x402 payment requirements to purchase the Pro quota tier.  Next: pay those terms, then commerce.activate_pro with the signature. | USE: Start Pro tier purchase / NOT: One-off resource pay only | free MCP tool tier; requires_env=['X402_PAY_TO_ADDRESS']; may trigger paid HTTP elsewhere | MCP → x402 requirements for Pro tier | Missing payTo env → cannot build requirements |
| `commerce.activate_pro` | Verify a Pro-tier x402 payment and unlock Pro quota limits for the agent.  Call after commerce.pro_requirements and a completed USDC payment. | USE: Finish Pro unlock after pay / NOT: Before payment exists | free MCP tool tier; may trigger paid HTTP elsewhere | MCP after Pro payment signature | Bad/missing signature → activate fails (body unknown) |
| `commerce.credits_requirements` | Build x402 payment requirements to buy a pack of per-use MCP tool credits.  Next: pay those terms, then commerce.purchase_credits with the signature. | USE: Start credits pack purchase / NOT: Pro already covers quota | free MCP tool tier; requires_env=['X402_PAY_TO_ADDRESS']; may trigger paid HTTP elsewhere | MCP → x402 requirements for credits pack | Missing payTo env → cannot build requirements |
| `commerce.purchase_credits` | Verify an x402 payment and add per-use tool credits to the agent.  Call after commerce.credits_requirements and a completed USDC payment. | USE: Finish credits unlock after pay / NOT: Before payment exists | free MCP tool tier; may trigger paid HTTP elsewhere | MCP after credits payment signature | Bad/missing signature → purchase fails (body unknown) |
| `commerce.stripe_checkout` | Create a Stripe Checkout Session for Pro tier or tool credits (fiat rail).  Use when the buyer pays by card instead of USDC; webhook fulfills the grant. | USE: Fiat card/bank instead of USDC / NOT: Pure crypto agents w/o Stripe | free MCP tool tier; requires_env=['STRIPE_SECRET_KEY']; may trigger paid HTTP elsewhere | POST https://x402-mcp.onrender.com/stripe/checkout (fiat rail) | Stripe misconfig → 4xx (body unknown without keys) |
| `swarm.research` | Run the swarm agency: compose a research product from free inputs and list it for resale.  Pass allow_paid_inputs=true only when buying upstream x402 services is intended. | USE: Swarm research product path / NOT: Simple city compliance check | free MCP tool tier; requires_env=['EVM_PRIVATE_KEY', 'X402_PAY_TO_ADDRESS']; may trigger paid HTTP elsewhere | MCP swarm research job | unknown |
| `swarm.settle` | Verify and settle a buyer's x402 payment for a listed composite product and record revenue.  Call with product_id plus PAYMENT-SIGNATURE after the buyer pays. | USE: Purchase swarm product / NOT: Free catalog browsing | paid swarm purchase; README $0.25 USDC (atomic not re-probed here) | GET https://x402-mcp.onrender.com/swarm/products/{id}/purchase → paid $0.25 path (README) | Unpaid purchase expected 402 (confirm per product id) |
| `swarm.revenue` | Get swarm portfolio revenue intelligence: spend, revenue, LTV:CAC, margins, per-source scores.  Call after swarm.research or swarm.settle to inspect realized economics. | USE: Swarm revenue read / NOT: Single city check buyers | free MCP tool tier; may trigger paid HTTP elsewhere | MCP revenue summary for swarm products | unknown |
| `pulse.base` | Get live Base Network Pulse: base fee, EIP-1559 projection, utilization, USD settlement cost, verdict.  Call before settling on Base when you need a settle-now vs hold recommendation. | USE: Base fee/settlement intelligence / NOT: City housing compliance | free MCP tool tier; may trigger paid HTTP elsewhere | MCP Base network pulse / EIP-1559 intelligence | unknown |
| `ops.metrics` | Get host OS telemetry: CPU, memory, swap, disk, network, and an ok/warn/critical health verdict.  Call to diagnose this MCP host; set include_processes=true for top memory processes. | USE: Ops health / quota burn / NOT: End-user property check | free MCP tool tier; may trigger paid HTTP elsewhere | https://x402-mcp.onrender.com/dashboard (ops surface) | Dashboard HTML 200 when up; MCP error unknown |
| `city.list` | List US City Open-Data Compliance Network cities with paid_url, sample_url, and price.  Call first, then city.sample, then city.check for the paid address lookup. | USE: List US city jurisdictions / NOT: City code already known | free MCP tool tier; may trigger paid HTTP elsewhere | GET https://x402-mcp.onrender.com/us/cities (free JSON catalog) | HTTP non-200 if host down |
| `city.sample` | Get a free fixed-address property compliance sample for one US city code.  Use before city.check to validate city_code and response shape without paying. | USE: Free example payload shape / NOT: Production licensed verdict | free MCP tool tier; may trigger paid HTTP elsewhere | GET https://x402-mcp.onrender.com/mn/property-check/sample (free sample) | HTTP non-200 if host down |
| `city.check` | Run a paid US city property compliance check via x402 on the same HTTP resource buyers use.  Prefer city.sample first. Settles USDC when EVM_PRIVATE_KEY is set; otherwise returns a 402 probe. | USE: Paid compliance verdict for address / NOT: Discovery-only — use list/sample | paid HTTP behind tool; live 402 amount=10000 atomic ($0.01 USDC) on Base | GET https://x402-mcp.onrender.com/us/mn/property-check?address=… (paid $0.01; 402 unpaid) | Unpaid GET → HTTP 402 `{"error":"payment_required","price":"$0.01"}` + payment-required accepts[] |
| `mailrail.send` | Dispatch transactional receipts, alert notifications, or agent communication over MailRail.  Supports mock ledger, Resend API, SMTP, or Webhooks. | USE: Send via MailRail / NOT: x402 HTTP resource payment | free MCP tool tier; may trigger paid HTTP elsewhere | MCP outbound mailrail message | unknown |
| `mailrail.status` | Inspect MailRail provider status, active sender address, and dispatch capabilities.  Call to verify communication rail readiness before dispatching receipts or alerts. | USE: Check MailRail delivery state / NOT: City checks | free MCP tool tier; may trigger paid HTTP elsewhere | MCP mailrail status | unknown |
| `mailrail.inbound` | Ingest or route an inbound message to the MailRail Postmaster agent with mention defusing and inbox ledger recording. | USE: Poll inbound MailRail / NOT: Outbound-only flows | free MCP tool tier; may trigger paid HTTP elsewhere | MCP inbound mailrail poll | unknown |

## Live 402 probe (city.check path)

```
GET https://x402-mcp.onrender.com/us/mn/property-check?address=1700+Penn+Ave+N
→ HTTP 402
body.error=payment_required
body.price=$0.01
header payment-required: x402 v2 JSON; accepts[].payTo=0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e; amount=10000; network eip155:8453
```

## Counts

- TOOL_SPECS entries scored: **23** (issue text target 16; registry currently ships 23).
- No `app/` edits in this change.

## Citations

- `app/tools_registry.py`
- https://x402-mcp.onrender.com/.well-known/mcp
- https://x402-mcp.onrender.com/us/cities
- https://x402-mcp.onrender.com/us/mn/property-check?address=1700+Penn+Ave+N (402)
- https://github.com/kwizzlesurp10-ctrl/x402-mcp/issues/494
