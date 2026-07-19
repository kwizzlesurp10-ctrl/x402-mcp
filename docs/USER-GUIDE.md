# x402-MCP User Guide — Operations & Financial Profit

A practical guide to running the x402 Micropayments MCP server, collecting revenue, controlling agent spend, and positioning Stripe as your primary payment rail with Coinbase/x402 crypto as an alternate (and future) rail.

**Audience:** Operators, developers, and agent builders who want MCP tool access and x402 micropayments to be **net profitable** — revenue from subscriptions, credits, and API fees should exceed what agents spend on external paid APIs.

**Related docs:** [SETUP.md](SETUP.md) (install), [agent-ops.md](agent-ops.md) (multi-agent cost control), [runbook.md](runbook.md) (operations), [architecture.md](architecture.md) (system design).

---

## 1. What x402-MCP is

x402-MCP is a production MCP server that connects AI agents (Cursor, Grok, Claude Desktop) to the [x402 HTTP micropayment protocol](https://x402.org). Agents can:

- **Discover** paid HTTP APIs in the x402 Bazaar
- **Probe** endpoints for `402 Payment Required` headers
- **Pay and fetch** protected resources with USDC on Base
- **Sell** access to your own APIs via x402 seller flows
- **Monetize MCP usage** via Pro tier upgrades and per-use tool credits

The server ships **11 MCP tools**, a **commerce overlay** (quota, tiers, `meta` envelope on every response), and **two payment rails** for upgrades:

| Rail | Status | Best for |
|------|--------|----------|
| **Stripe** | Primary, production-ready | Card/bank checkout; no crypto wallet for buyers |
| **x402 / Coinbase CDP** | Alternate / future | On-chain USDC; agent-native micropayments; CDP facilitator in production |

Check which rail is active:

```bash
curl http://localhost:8402/upgrade
curl http://localhost:8402/health
```

`/upgrade` returns `payment_rails.stripe.configured` and `payment_rails.x402_coinbase.configured` booleans plus step-by-step flows for each.

---

## 2. How profit works (three revenue layers)

Think of profit as three stacked layers. You can run one or all three.

### Layer A — MCP commerce (tool access fees)

Agents call your MCP server. Free tier is generous (500 calls/month, 10/min) to drive adoption. Revenue comes when users upgrade:

| Product | Default price | Fulfillment |
|---------|---------------|-------------|
| **Pro tier** | $29/month equivalent | 50,000 calls/month, 120/min rate limit |
| **Tool credits** | $1 per 100 credits | Extra calls when monthly quota is exhausted |

**Stripe path (recommended for humans):**

1. Buyer calls `create_stripe_checkout` (MCP) or you `POST /stripe/checkout`
2. Buyer completes payment at `checkout_url`
3. Stripe sends webhook to `POST /stripe/webhook`
4. Server unlocks Pro tier or adds credits (idempotent per payment)

**x402/Coinbase path (agents & crypto-native buyers):**

1. `get_pro_upgrade_requirements` or `get_tool_credits_requirements`
2. Buyer pays on-chain to your `X402_PAY_TO_ADDRESS`
3. `activate_pro_tier` or `purchase_tool_credits` with `PAYMENT-SIGNATURE`

Stripe settles to your **Stripe balance** (fiat). x402 settles to your **wallet** (USDC on-chain).

### Layer B — Seller APIs (per-request micropayments)

You publish HTTP endpoints that return `402` with x402 payment headers. Each successful payment sends USDC to `X402_PAY_TO_ADDRESS`.

1. Configure `X402_PAY_TO_ADDRESS` (your receive wallet)
2. Call `build_seller_requirements` to generate `PAYMENT-REQUIRED` payloads
3. Attach those headers to your API routes
4. Buyers pay; you verify with `verify_payment_payload`
5. List your service in the Bazaar via `discover_services` discovery index

This is **per-call revenue** — ideal for data APIs, inference endpoints, or premium agent tools exposed over HTTP.

### Layer C — Cost control (keeping spend below revenue)

If your agents also **buy** external x402 APIs (`pay_and_fetch`), spend can eat profit. The **agent-ops** operating group (scout → archivist → warden → treasurer → merchant) enforces a cost ladder so the group trends toward **net ≥ 0**. See [Section 8](#8-agent-ops-cost-effective-to-free).

**Net position formula:**

```
net = Σ revenue (Stripe + on-chain seller + MCP x402 upgrades)
    − Σ mainnet spend (pay_and_fetch on eip155:8453)
```

Testnet spend (`eip155:84532`) counts as **$0.00** for budgeting.

---

## 3. Quick start (15 minutes)

### Install

```powershell
cd path\to\x402-mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

### Minimum config for profit

Edit `.env`:

```env
# Where on-chain revenue lands (seller + x402 commerce)
X402_PAY_TO_ADDRESS=0xYourReceiveWallet

# Stripe (primary fiat rail)
STRIPE_SECRET_KEY=sk_live_...          # or sk_test_... for sandbox
STRIPE_WEBHOOK_SECRET=whsec_...

# Public URLs (update before production)
PUBLIC_BASE_URL=https://your-mcp.example.com
UPGRADE_URL=https://your-site.example.com/upgrade
```

### Run

**Local MCP (Cursor):**

```powershell
python run_stdio.py
```

Wire `manifests/cursor-mcp.json` into Cursor MCP settings.

**HTTP / remote connector:**

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8402
```

Verify:

```powershell
curl http://localhost:8402/health
curl http://localhost:8402/.well-known/mcp
curl http://localhost:8402/upgrade
```

### First smoke test

In Cursor or via MCP client, call `get_supported_networks` with a stable `agent_id`:

```json
{ "agent_id": "my-agent-01" }
```

Expect `data` (networks list) plus `meta` with `quota_remaining`, `tier`, and `agent_id`. Every tool response uses this envelope — use it to monitor usage and upsell before quota exhaustion.

---

## 4. Payment rails in depth

### 4.1 Stripe (primary — use this for most revenue today)

Stripe is the **default** rail for Pro tier and tool-credit purchases. Buyers pay with card or bank; you receive fiat in your Stripe account.

#### Stripe Dashboard setup

1. Create a [Stripe account](https://dashboard.stripe.com/register)
2. **Developers → API keys** — copy Secret key → `STRIPE_SECRET_KEY`
3. **Developers → Webhooks** — add endpoint:
   - URL: `https://your-mcp.example.com/stripe/webhook`
   - Events: `checkout.session.completed`, `payment_intent.succeeded`
   - Copy signing secret → `STRIPE_WEBHOOK_SECRET`
4. For local testing, use [Stripe CLI](https://stripe.com/docs/stripe-cli):
   ```bash
   stripe listen --forward-to localhost:8402/stripe/webhook
   ```

#### Create a checkout (MCP tool)

```json
{
  "purpose": "pro_tier_upgrade",
  "agent_id": "buyer-agent-01"
}
```

Tool: `create_stripe_checkout`

Response includes `checkout_url` — send the buyer there. After payment, the webhook fulfills automatically.

#### Create a checkout (HTTP API)

```bash
curl -X POST http://localhost:8402/stripe/checkout \
  -H "Content-Type: application/json" \
  -d '{"purpose":"tool_credits","agent_id":"buyer-agent-01","credits":100}'
```

#### Tool credits purchase

```json
{
  "purpose": "tool_credits",
  "agent_id": "buyer-agent-01",
  "credits": 100
}
```

Default pack is 100 credits at $1.00 (configurable via `TOOL_CREDIT_PACK_SIZE` and `TOOL_CREDIT_PACK_PRICE`).

#### Idempotency

Webhooks use fulfillment keys (`pi:...` or `cs:...`) so duplicate Stripe events do not double-grant Pro tier or credits. Safe to retry webhooks.

#### Profit checklist (Stripe)

- [ ] Live Stripe keys in production `.env`
- [ ] Webhook endpoint reachable from Stripe (HTTPS required)
- [ ] `PUBLIC_BASE_URL` matches your deployed host (success/cancel URLs)
- [ ] `UPGRADE_URL` points to a landing page explaining Pro tier value
- [ ] Test full flow: checkout → pay → webhook → `GET /stats` shows tier change

---

### 4.2 x402 / Coinbase (alternate & future rail)

The x402 rail lets agents pay with **USDC on Base** without Stripe. Coinbase Developer Platform (CDP) provides the production facilitator and Bazaar discovery index.

#### Testnet (free — develop and demo)

```env
X402_FACILITATOR_URL=https://x402.org/facilitator
X402_DEFAULT_NETWORK=eip155:84532
X402_PAY_TO_ADDRESS=0xYourTestnetReceiveWallet
```

Fund a buyer wallet via the [CDP Faucet](https://docs.cdp.coinbase.com/faucets/introduction/quickstart) (Base Sepolia ETH + USDC).

**Pro tier via x402:**

1. `get_pro_upgrade_requirements` → payment requirements with your `pay_to`
2. Buyer wallet signs and pays
3. `activate_pro_tier` with `payment_signature` + `payment_required`

**Tool credits via x402:**

1. `get_tool_credits_requirements`
2. `purchase_tool_credits` after on-chain payment

Revenue lands in `X402_PAY_TO_ADDRESS` on-chain.

#### Production mainnet (Coinbase CDP — future-ready)

When you are ready for real USDC:

```env
X402_FACILITATOR_URL=https://api.cdp.coinbase.com/platform/v2/x402
X402_DEFAULT_NETWORK=eip155:8453
CDP_API_KEY_ID=your_key
CDP_API_KEY_SECRET=your_secret
X402_PAY_TO_ADDRESS=0xYourMainnetReceiveWallet
```

`/upgrade` labels this rail `alternate_future_rail` in the API response — it is fully implemented for MCP commerce and seller flows; CDP production facilitator is the path for mainnet settlement at scale.

#### When to use x402 vs Stripe

| Scenario | Recommended rail |
|----------|------------------|
| Human upgrades from a web page | **Stripe** |
| Agent autonomously buys Pro/credits | **x402** |
| Per-request API monetization | **x402** (native 402 headers) |
| No crypto wallet for buyers | **Stripe** |
| Micropayments <$1, agent-to-agent | **x402** |

**Practical strategy:** Offer **both**. Default your upgrade landing page to Stripe Checkout; expose x402 tools for agent workflows. Revenue from either rail counts toward profitability.

---

## 5. MCP tools reference

| Tool | Role | Wallet / keys | Revenue impact |
|------|------|---------------|----------------|
| `discover_services` | Find paid APIs | None | Indirect — finds APIs to resell or use |
| `get_payment_requirements` | Probe 402 price | None | Cost control — verify price before paying |
| `pay_and_fetch` | Buy external API access | `EVM_PRIVATE_KEY` | **Spend** — treasurer only |
| `build_seller_requirements` | Create seller 402 config | `X402_PAY_TO_ADDRESS` | **Revenue** — enables per-call fees |
| `verify_payment_payload` | Confirm buyer paid | None | **Revenue** — gate access after payment |
| `get_supported_networks` | Reference | None | Free |
| `get_pro_upgrade_requirements` | x402 Pro invoice | `X402_PAY_TO_ADDRESS` | **Revenue** |
| `activate_pro_tier` | Fulfill x402 Pro | None | **Revenue** |
| `get_tool_credits_requirements` | x402 credits invoice | `X402_PAY_TO_ADDRESS` | **Revenue** |
| `purchase_tool_credits` | Fulfill x402 credits | None | **Revenue** |
| `create_stripe_checkout` | Stripe Checkout | `STRIPE_SECRET_KEY` | **Revenue** (primary) |

Canonical inventory: `app/tools_registry.py`. Manifest: `GET /.well-known/mcp`.

---

## 6. Commerce overlay (every response)

Every tool returns:

```json
{
  "data": { },
  "meta": {
    "tier": "free",
    "calls_this_month": 42,
    "quota_remaining": 458,
    "quota_warning": false,
    "rate_limit_remaining": 7,
    "tool_credits_remaining": 0,
    "upgrade_url": "https://your-site.example.com/upgrade",
    "agent_id": "buyer-agent-01"
  }
}
```

**Operator tips:**

- Always pass a **stable `agent_id`** — omitting it creates throwaway UUIDs and breaks quota tracking
- `quota_warning: true` means ≥80% of monthly quota used — upsell Pro or credits
- `rate_limit_remaining` hits 0 at 10 calls/min on free tier — Pro tier raises to 120/min
- In-memory store resets on server restart — set `REDIS_URL` before taking real money

**Tier defaults:**

| Tier | Monthly quota | Rate limit | Price |
|------|---------------|------------|-------|
| Free | 500 | 10/min | $0 |
| Pro | 50,000 | 120/min | $29 (Stripe or x402) |

---

## 7. Profit playbook (step by step)

### Phase 1 — Validate (testnet, $0 risk)

1. Set `X402_DEFAULT_NETWORK=eip155:84532`
2. Fund a test buyer wallet from CDP faucet
3. Run `discover_services` → `get_payment_requirements` → `pay_and_fetch` on a test endpoint
4. Run `build_seller_requirements` with your test `X402_PAY_TO_ADDRESS`
5. Confirm `verify_payment_payload` accepts a test payment
6. Run `pytest -v` — all tests should pass

### Phase 2 — Stripe revenue (fiat)

1. Configure Stripe test keys
2. `create_stripe_checkout` for `pro_tier_upgrade`
3. Complete test payment with card `4242 4242 4242 4242`
4. Confirm webhook fulfillment: agent tier flips to `pro` in `/stats`
5. Swap to live keys; update `PUBLIC_BASE_URL` and webhook URL

### Phase 3 — Publish seller APIs (per-call USDC)

1. Deploy `uvicorn` with HTTPS and `PUBLIC_BASE_URL`
2. Integrate x402 middleware on your premium routes (402 + `PAYMENT-REQUIRED`)
3. Set competitive `X402_DEFAULT_PRICE` (default `$0.01`/call)
4. Ensure your endpoint appears in Bazaar discovery
5. Log verified payments to `ledger/revenue.jsonl` (agent-ops merchant)

### Phase 4 — Scale & harden

1. Set `REDIS_URL` for durable quota (required before real revenue)
2. Deploy Stripe webhooks on a stable HTTPS endpoint
3. Enable CDP mainnet facilitator when ready for on-chain revenue at scale
4. Monitor `GET /stats`, `GET /ledger/spend`, `GET /ledger/revenue`
5. Tune `ledger/policy.json` caps as spend grows

### Pricing levers

| Lever | Env / file | Effect |
|-------|------------|--------|
| Pro price | `PRO_TIER_PRICE` | Subscription revenue |
| Credit pack | `TOOL_CREDIT_PACK_PRICE`, `TOOL_CREDIT_PACK_SIZE` | Per-call overflow revenue |
| API price | `X402_DEFAULT_PRICE` | Per-request seller revenue |
| Free quota | `FREE_TIER_MONTHLY_QUOTA` | Conversion funnel width |
| Spend caps | `ledger/policy.json` | Agent ops cost ceiling |

---

## 8. Agent ops (cost-effective-to-free)

For teams running **multiple agents** that both earn and spend, use the five subagents in `.claude/agents/`:

| Agent | Job | Pays? |
|-------|-----|-------|
| `x402-scout` | Discover + probe | Never |
| `x402-archivist` | Cache responses | Never |
| `x402-warden` | Approve/deny spend | Never |
| `x402-treasurer` | `pay_and_fetch` only | Yes (vault instance) |
| `x402-merchant` | Seller + Stripe + x402 revenue | Never (collects) |

**Two-instance topology** (security + cost isolation):

```
Instance A — "free" (no EVM_PRIVATE_KEY)     Instance B — "vault" (EVM_PRIVATE_KEY)
  scout, warden, archivist, merchant          treasurer ONLY
```

Copy `.mcp.json.example` → `.mcp.json` (git-ignored).

**Budget policy** (`ledger/policy.json`):

```json
{
  "max_price_per_call_usdc": 0.05,
  "daily_cap_usdc": 0.50,
  "monthly_cap_usdc": 3.00,
  "require_testnet_first": true,
  "receive_wallet": "0xYourWallet"
}
```

**Mission control API** (read-only dashboard backend):

| Endpoint | Returns |
|----------|---------|
| `GET /stats` | Per-agent quota snapshot + config |
| `GET /events` | SSE stream of tool invocations |
| `GET /ledger/spend` | Spend rows (JSON array, newest first) |
| `GET /ledger/revenue` | Revenue rows (JSON array, newest first) |

Goal: **net position ≥ 0** — merchant + Stripe revenue offsets treasurer mainnet spend.

Full detail: [agent-ops.md](agent-ops.md).

---

## 9. Connecting clients

### Cursor (stdio)

```json
{
  "mcpServers": {
    "x402": {
      "command": "python",
      "args": ["${workspaceFolder}/run_stdio.py"],
      "env": {
        "X402_PAY_TO_ADDRESS": "0xYourWallet",
        "STRIPE_SECRET_KEY": "sk_test_..."
      }
    },
    "x402vault": {
      "command": "python",
      "args": ["${workspaceFolder}/run_stdio.py"],
      "env": {
        "EVM_PRIVATE_KEY": "${X402_TESTNET_KEY}",
        "X402_DEFAULT_NETWORK": "eip155:84532"
      }
    }
  }
}
```

Keep private keys in environment variables, never in committed JSON.

### Grok / HTTP connector

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8402
```

Manifest URL: `https://your-host/.well-known/mcp`  
MCP SSE: `https://your-host/mcp/sse`

Set `PUBLIC_BASE_URL` so `connector_url` in the manifest is correct.

### Docker

```bash
docker build -f deployment/Dockerfile -t x402-mcp .
docker run -p 8402:8402 --env-file .env x402-mcp
```

---

## 10. Monitoring profitability

### Daily operator checks

```bash
# Service health
curl https://your-host/health

# Who is using quota?
curl https://your-host/stats

# Spend vs revenue (agent-ops ledger)
curl https://your-host/ledger/spend
curl https://your-host/ledger/revenue
```

### Stripe Dashboard

- **Payments** — fiat revenue
- **Webhooks** — confirm `checkout.session.completed` deliveries succeed
- **Disputes** — handle chargebacks on Pro tier

### On-chain

- Monitor `X402_PAY_TO_ADDRESS` on [BaseScan](https://basescan.org) (mainnet) or [Sepolia BaseScan](https://sepolia.basescan.org) (testnet)
- Match `ledger/revenue.jsonl` entries to transactions

### Warning signs

| Signal | Action |
|--------|--------|
| `quota_warning: true` on many agents | Raise Pro conversion; add Stripe checkout link to `upgrade_url` |
| Mainnet spend rising in `/ledger/spend` | Tighten `ledger/policy.json`; enforce testnet-first |
| Webhook failures in Stripe | Fix HTTPS endpoint; rotate `STRIPE_WEBHOOK_SECRET` |
| Net position negative 7+ days | Merchant raises `X402_DEFAULT_PRICE`; warden lowers caps |

---

## 11. Environment reference

| Variable | Required for | Notes |
|----------|--------------|-------|
| `STRIPE_SECRET_KEY` | Stripe checkout | Primary fiat rail |
| `STRIPE_WEBHOOK_SECRET` | Webhook fulfillment | Required for auto Pro/credits |
| `STRIPE_PUBLISHABLE_KEY` | Frontend Stripe.js | Optional; for embedded checkout |
| `X402_PAY_TO_ADDRESS` | Seller + x402 commerce | On-chain profit wallet |
| `EVM_PRIVATE_KEY` | `pay_and_fetch` | Buyer spend — separate hot wallet |
| `X402_FACILITATOR_URL` | x402 verify/pay | Testnet or CDP production |
| `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` | CDP production | Future mainnet facilitator |
| `X402_DEFAULT_NETWORK` | Network selection | `eip155:84532` testnet, `eip155:8453` mainnet |
| `PUBLIC_BASE_URL` | Manifest + Stripe URLs | Must match deployed host |
| `UPGRADE_URL` | Commerce meta | Your marketing/upgrade page |
| `REDIS_URL` | Durable quota | **Required before real revenue** |
| `PRO_TIER_PRICE` | Pro pricing | Default `$29.00` |
| `TOOL_CREDIT_PACK_SIZE` | Credits pack | Default `100` |
| `TOOL_CREDIT_PACK_PRICE` | Credits pricing | Default `$1.00` |

---

## 12. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `STRIPE_SECRET_KEY required` | Stripe not configured | Add keys to `.env`; use x402 alternate if intentional |
| Webhook returns 400 | Bad signature | Match `STRIPE_WEBHOOK_SECRET`; use raw body |
| Pro not activated after Stripe pay | Webhook not received | Check Stripe CLI / dashboard deliveries |
| `X402_PAY_TO_ADDRESS required` | Seller/commerce tools | Set receive wallet in `.env` |
| `EVM_PRIVATE_KEY required` | Buyer tool without wallet | Set buyer key on vault instance only |
| `429 rate_limit_exceeded` | Free tier 10/min | Wait 60s or upgrade to Pro |
| `monthly_quota_exceeded` | 500 calls used | Stripe checkout or x402 credits |
| Quota resets unexpectedly | In-memory store | Set `REDIS_URL` |
| `pay_and_fetch` overpays | No server-side price cap | Warden must approve from probe first |
| MCP tools missing in Cursor | Bad path in MCP config | Fix `run_stdio.py` path; restart Cursor |

---

## 13. Security checklist

- [ ] Never commit `.env`, `.mcp.json`, or `ledger/spend.jsonl` / `revenue.jsonl`
- [ ] `chmod 600 .env` on Unix; restrict Windows ACLs
- [ ] Separate **receive wallet** (`X402_PAY_TO_ADDRESS`) from **buyer hot wallet** (`EVM_PRIVATE_KEY`)
- [ ] Treasurer runs on isolated vault instance (stdio only, no public HTTP)
- [ ] Stripe webhook signature verification always enabled
- [ ] `# TODO auth` on ops endpoints before public exposure (`/stats`, `/events`, `/ledger/*`)
- [ ] Rotate any key that appears in logs or chat immediately

---

## 14. Testing

```powershell
.\.venv\Scripts\python -m pytest -v
.\.venv\Scripts\python scripts\verify_goal.py
```

Expected without wallets: seller and buyer tools return clear configuration errors — not crashes. With Stripe test keys: `tests/test_stripe*.py` exercises checkout and webhook idempotency.

---

## 15. Variant note: `x402` vs `x402-mcp`

| Repo | Tools | Stripe | Agent ops |
|------|-------|--------|-----------|
| **x402-mcp** (this guide) | 11 | Yes (`create_stripe_checkout`) | Yes |
| **x402** | 10 | No (x402 commerce only) | Yes |

If you use the slimmer `x402` repo, follow this guide for x402/Coinbase flows and agent ops; add Stripe by migrating to `x402-mcp` or porting `app/stripe_payments.py`.

---

## 16. Summary — path to profit

1. **Deploy** HTTP server with `PUBLIC_BASE_URL` and health checks
2. **Configure Stripe** as primary upgrade rail; test webhook fulfillment
3. **Set `X402_PAY_TO_ADDRESS`** for on-chain seller and agent-commerce revenue
4. **Publish** paid APIs with `build_seller_requirements` + Bazaar discovery
5. **Control spend** with agent-ops warden caps and treasurer-only payments
6. **Harden** with `REDIS_URL` before accepting real payments
7. **Enable CDP mainnet** when ready to scale crypto-native revenue
8. **Monitor** `/stats`, ledgers, Stripe Dashboard, and on-chain wallet

Revenue from Stripe (fiat) + x402 (USDC) + seller APIs (per-call) should exceed agent mainnet spend. That is the operating thesis: **cost-effective-to-free** at the group level, **profitable** at the operator level.