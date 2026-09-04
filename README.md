# x402 Micropayments MCP

[![LightNow capabilities](https://lightnow.ai/badge/io.github.kwizzlesurp10-ctrl/x402-mcp)](https://lightnow.ai/servers/io.github.kwizzlesurp10-ctrl/x402-mcp)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Base Mainnet](https://img.shields.io/badge/Network-Base%20Mainnet%20(8453)-0052FF.svg)](https://base.org)
[![A2A Protocol](https://img.shields.io/badge/Identity-A2A%20v1.0%20Agent%20Card-green.svg)](https://x402-mcp.onrender.com/.well-known/agent-card.json)

Production MCP server for the [x402](https://x402.org) HTTP micropayment protocol — **live on Base mainnet, selling real data products to AI agents for USDC today**. Agents discover paid services, probe `402 Payment Required` responses, pay with stablecoins, and build/verify seller payment configs; the server runs both sides of that market.

## Discover (public + A2A)

Machine surfaces agents and directories crawl first:

| Surface | URL |
|---------|-----|
| A2A Agent Card | https://x402-mcp.onrender.com/.well-known/agent-card.json |
| Agents registry | https://x402-mcp.onrender.com/.well-known/agents.json |
| x402 catalog | https://x402-mcp.onrender.com/.well-known/x402 |
| Funding / payTo | https://x402-mcp.onrender.com/.well-known/funding.json |
| MCP manifest | https://x402-mcp.onrender.com/.well-known/mcp |
| MCP server card | https://x402-mcp.onrender.com/.well-known/mcp/server-card.json |
| LLM docs | https://x402-mcp.onrender.com/llms.txt |
| OpenAPI | https://x402-mcp.onrender.com/openapi.json |
| Free city catalog | https://x402-mcp.onrender.com/us/cities |

Agent Card declares the [a2a-x402](https://github.com/google-a2a/a2a-x402) extension, AP2-style `payments.rails[]` (USDC on Base), and explicit `funding.payTo`.

## Fund (USDC on Base)

Payment for delivered products / documentation artifacts, or a voluntary tip. **Not a token, not equity, not a raise.**

| Field | Value |
|-------|-------|
| Network | Base `eip155:8453` |
| Asset | USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| payTo | `0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e` |
| Explorer | https://basescan.org/address/0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e |
| Machine cashier | buy any live paid endpoint (e.g. $0.01 property-check) |
| Bounties protocol | [docs/BOUNTIES.md](docs/BOUNTIES.md) · [open a bounty](https://github.com/kwizzlesurp10-ctrl/x402-mcp/issues/new?template=paid-bounty.md) |
| GitHub FUNDING.yml | [.github/FUNDING.yml](.github/FUNDING.yml) |

Fiat Sponsors (GitHub Sponsors / Polar / thanks.dev) do **not** credit `payTo` on-chain.

## Live on Base mainnet

**Storefront:** https://x402-mcp.onrender.com — x402 v2 challenges served, USDC verified + settled through the Coinbase CDP facilitator (`eip155:8453`).

| Product | Price | What you get |
|---------|-------|--------------|
| `GET /mn/property-check?address=…` | $0.01 USDC | Minneapolis rental-compliance snapshot composed from 3 live City of Minneapolis open datasets — the first machine-payable housing-compliance data for agents |
| `GET /us/{code}/property-check?address=…` | $0.01 USDC | **US City Open-Data Compliance Network** (14 jurisdictions) — same wire protocol; free catalog `/us/cities` + free `/sample`; MCP: `city.list` → `city.sample` → `city.check` |
| `GET /swarm/products/{id}/purchase` | $0.25 USDC | Base Network Pulse: live settlement-conditions intelligence (EIP-1559 math + real RPC + ETH spot), listed with the x402 Bazaar discovery extension |

The public seller host holds **no spend key** — it only verifies and settles inbound payments ([docs/SELLER-STOREFRONT.md](docs/SELLER-STOREFRONT.md)). Roadmap: [ROADMAP.md](ROADMAP.md).

## Features

- **19 MCP tools** for buyer, seller, Stripe fiat, x402 commerce, swarm-agency, US city compliance, and ops-monitoring flows — canonical inventory in `app/tools_registry.py` (single source for README, `/.well-known/mcp`, and tests); guarded by `tests/test_readme.py` and `tests/test_manifest.py`
- **4 MCP prompts** (`onboarding_flow`, `x402_tool_selector`, `generate_quote`, `troubleshoot_payment`) for LLM orchestrators
- **4 MCP resources** (`x402://agent-card`, `x402://server-card`, `x402://tools-manifest`, `x402://pricing-table`) exposing live machine descriptors
- **A2A Protocol v1.0 Agent ID Cards** — HTTP Agent Card + MCP `get_agent_card` / `x402://agent-card` with per-`agent_id` quota isolation
- **x402/Coinbase rail** (primary): x402 v2 wire format end to end — challenge generation, verify + settle via the CDP facilitator on Base mainnet, Bazaar discoverability on listings
- **Stripe payment rail** (fiat alternative): `commerce.stripe_checkout` + `POST /stripe/checkout` + `POST /stripe/webhook` for card/bank payments
- **Commerce overlay:** 500 calls/month, 10/min rate limit, `meta` envelope on every response
- **FastMCP** + **FastAPI** with `/.well-known/mcp` manifest
- **stdio** (Cursor/Grok local) and **HTTP/SSE** (remote connector) transports
- **Redis-ready** quota store (in-memory default)
- **Operator dashboard** at `/dashboard` — live health, per-agent quota burn-down meters, tool matrix, and revenue paths (single-file, zero build step)
- **Hermetic test suite** — a local mock facilitator/discovery backend spins up automatically; no internet required. Set `X402_LIVE_TESTS=1` to run against x402.org

## Quickstart & 1-Click Installation

Install `kwizzlesurp10/x402-mcp` into your favorite MCP client using the [Smithery CLI](https://smithery.ai/server/kwizzlesurp10/x402-mcp):

```bash
# Claude Desktop
npx -y @smithery/cli install kwizzlesurp10/x402-mcp --client claude

# Cursor
npx -y @smithery/cli install kwizzlesurp10/x402-mcp --client cursor

# Windsurf
npx -y @smithery/cli install kwizzlesurp10/x402-mcp --client windsurf
```

## Quick Start (Mission Control)

```bash
git clone <repo> && cd x402-mcp
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt && cd dashboard && pnpm install && cd ..
cp .env.example .env
make up
```

Open http://localhost:5173 — setup wizard runs with doctor checks. Toggle **Demo** to preview every panel with zero wallet.

**Docs:** [docs/SETUP.md](docs/SETUP.md) · [docs/USER-GUIDE.md](docs/USER-GUIDE.md) · [docs/UI-HANDOFF-v2.md](docs/UI-HANDOFF-v2.md)

### Local stdio (Cursor)

```bash
python run_stdio.py
```

Add to Cursor MCP config (`manifests/cursor-mcp.json`).

### HTTP server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8402
curl http://localhost:8402/.well-known/mcp
curl http://localhost:8402/health
# then open http://localhost:8402/dashboard
```

## Paid HTTP Resource: MN Property Check

First-party sellable endpoint (the seller side of this repo's own tooling):

```
GET /mn/property-check?address=1700%20Penn%20Ave%20N
```

x402-gated at **$0.01 USDC** (`MN_PROPERTY_CHECK_PRICE`). Unpaid requests get a
`402` with x402 v2 `PAYMENT-REQUIRED` terms; paid requests are verified and
settled via the facilitator, then served with a `PAYMENT-RESPONSE` receipt.

One call returns a composite Minneapolis rental-compliance snapshot from live
City of Minneapolis Open Data: active rental license (status, tier, licensed
units, expiration, ward/neighborhood), regulatory violation case history
(APN-joined), and condemned/boarded status. Owner phone/email in the source
data are intentionally never served. Public records, as-is; not legal advice.

## MCP Tools

Tool names use domain.action trees so clients can route `x402.*`, `commerce.*`, `swarm.*`, `pulse.*`, `ops.*`, and `city.*`.

| Tool | Description |
|------|-------------|
| `x402.discover` | Query x402 Bazaar for paid HTTP APIs |
| `x402.probe` | Probe URL for `PAYMENT-REQUIRED` on 402 |
| `x402.pay_and_fetch` | Auto-pay and fetch protected resource |
| `x402.build_seller` | Build seller payment requirements |
| `x402.verify` | Verify payment via facilitator |
| `x402.networks` | Networks, facilitators, v2 headers |
| `commerce.pro_requirements` | Build x402 payment requirements for Pro tier upgrade |
| `commerce.activate_pro` | Verify x402 payment and unlock Pro tier quota |
| `commerce.credits_requirements` | Build x402 payment requirements for per-use tool credits |
| `commerce.purchase_credits` | Verify x402 payment and add per-use tool credits |
| `commerce.stripe_checkout` | Create Stripe Checkout Session for pro tier or credits |
| `swarm.research` | Swarm Agency: compose a research report and list it for resale |
| `swarm.settle` | Verify + settle a buyer's payment for a listed composite and record revenue |
| `swarm.revenue` | Portfolio revenue intelligence: spend, revenue, LTV:CAC, margins, per-source profit scores |
| `pulse.base` | Live Base Network Pulse: synthesized settlement-conditions intelligence (base fee, utilization, USD cost, verdict) from real RPC data |
| `ops.metrics` | Host OS telemetry: CPU, memory, swap, disk, network, and process signals with an ok/warn/critical health verdict |
| `city.list` | Free US City Open-Data Compliance catalog (codes, paid_url, sample_url, MCP golden path) |
| `city.sample` | Free fixed-address property compliance sample for one city code |
| `city.check` | Paid city property compliance via x402 (same HTTP resource external buyers use) |

## Installation

### Smithery

[Install via Smithery](https://smithery.ai/servers/kwizzlesurp10/x402-mcp)

Remote Streamable HTTP (no install): `https://x402-mcp.onrender.com/mcp/mcp`

```bash
smithery mcp add https://x402-mcp.onrender.com/mcp/mcp --id x402-mcp
```

### Usage

Connect an MCP client to Streamable HTTP `/mcp/mcp`. Call `x402.discover` then `x402.probe` then `x402.pay_and_fetch` for paid APIs; `city.list` → `city.sample` → `city.check` for US property compliance.

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `X402_PAY_TO_ADDRESS` | For selling | Recipient wallet — all x402 sales settle here |
| `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` | For Base mainnet | Coinbase CDP facilitator creds (verify + settle on `eip155:8453`) |
| `SWARM_SELL_NETWORK` | For mainnet listings | Set `eip155:8453` to list products on Base mainnet (default: Base Sepolia) |
| `EVM_PRIVATE_KEY` | For `pay_and_fetch` | Buyer wallet private key — **never set this on a public seller host** |
| `STRIPE_SECRET_KEY` | For Stripe checkout | Fiat payment rail |
| `STRIPE_WEBHOOK_SECRET` | For `/stripe/webhook` | Webhook signature verification |
| `X402_FACILITATOR_URL` | No | Default: `https://x402.org/facilitator` (testnet; CDP handles mainnet) |
| `UPGRADE_URL` | No | Commerce tier upgrade link |

## Commerce Meta Envelope

Every tool response includes:

```json
{
  "data": { "...": "..." },
  "meta": {
    "tier": "free",
    "calls_this_month": 1,
    "quota_remaining": 499,
    "quota_warning": false,
    "rate_limit_remaining": 9,
    "upgrade_url": "https://forge.example.com/upgrade",
    "agent_id": "..."
  }
}
```

## Agent Ops / Swarm Agency

Cost-effective multi-agent operating group (scout, warden, treasurer, archivist, sovereign, merchant) with budget policy and ledger. See [docs/agent-ops.md](docs/agent-ops.md). Dashboard handoff: [docs/UI-HANDOFF.md](docs/UI-HANDOFF.md).

The **Swarm Agency** (`app/swarm/`) implements the hybrid resale loop end-to-end:
**scout** discovers cheap upstream x402 services → **warden** enforces `ledger/policy.json` spend caps → **treasurer** `pay_and_fetch`es and records cost basis to `ledger/spend.jsonl` → **archivist** composes a research report priced at `cost × SWARM_MARKUP` → **sovereign** (profit optimizer) reprices the composite to hit a target LTV:CAC (`SWARM_TARGET_LTV_CAC`, default 3.0), enforces a margin floor, and scores which upstream sources are actually profitable → **merchant** lists it via `build_seller_requirements`; `settle_composite_sale` records realized revenue. Portfolio economics (spend, revenue, LTV:CAC, per-source profit) surface via `swarm_revenue_report` / `GET /swarm/revenue`. Every phase streams to the dashboard's Swarm Activity panel over SSE. Run via the `run_swarm_research` MCP tool (needs `EVM_PRIVATE_KEY` + `X402_PAY_TO_ADDRESS`).

**Multi-chain (EVM + Solana).** The resource server registers `ExactEvmServerScheme` for `eip155:*` and `ExactSvmServerScheme` for `solana:*` (via the `x402[svm]` extra; `solana>=0.36,<0.40`). Seller requirements build on Base **and** Solana mainnet (`solana:EtWTRAB…`), and the buyer client registers an EVM and/or Solana signer from `EVM_PRIVATE_KEY` / `SVM_PRIVATE_KEY` — no marketing-vs-code gap.

**Selling network / facilitators.** The merchant lists on `SWARM_SELL_NETWORK` (default `eip155:84532`). The free `x402.org` facilitator only settles `exact` on Base Sepolia; to **sell/settle on Base mainnet** set `SWARM_SELL_NETWORK=eip155:8453` and provide Coinbase CDP credentials (`CDP_API_KEY_ID` + `CDP_API_KEY_SECRET`) — the seller then routes verify/settle through the CDP facilitator with a per-request Ed25519 JWT (`app/cdp_auth.py`).

## Base Network Pulse

**Base Network Pulse** (`app/pulse.py` + `app/swarm/publisher.py`) is a **synthesis** publisher: it turns free, high-quality Base RPC data (latest block, EIP-1559 base fee, block gas utilization) plus a live ETH spot price into a priced, x402-payable intelligence report. It projects the next-block base fee from the EIP-1559 formula, converts settlement gas into a live USD cost, and renders a **settle-now / hold** verdict on current Base settlement conditions. All inputs are **real data — no mocks**: real Base RPC calls, real Coinbase ETH price, real base-fee math.

Endpoints:

- `GET /pulse` — live preview of the current synthesized pulse (base fee, utilization, USD settlement cost, verdict).
- `POST /pulse/publish` — mints an x402-payable listing for the report (402-gated purchase endpoint).
- `get_base_pulse` MCP tool — the same intelligence surfaced to agents.

This is the **synthesis** economic model: cost basis is ~$0 because the underlying Base data is free to read; the margin is the analysis itself. The priced report is sold to external buyers through the 402-gated purchase endpoint — pure synthesized value on top of free public data.

## Testing

```bash
pytest -v
```

See [docs/SETUP.md](docs/SETUP.md#step-7--test-without-surprises) for expected vs unexpected errors (wallet tools fail clearly until `.env` is configured).

## Mission Control Dashboard

Fintech-terminal ops dashboard at `http://localhost:5173`. Net position, quota gauge, rate sparkline, activity stream, agent lanes, spend/revenue ledgers (with BaseScan links), 402 Inspector, wallet panel, first-run wizard, and mission progress tracker. Three density modes (Guided/Standard/Operator). `cmd+K` command palette.

API surface: `GET /stats`, `GET /events` (SSE with 15s heartbeat), `GET /ledger/{spend|revenue}`, `GET /doctor`, `GET /probe`, `GET /wallet`, `POST /seller/requirements`.

## Agent Ops

Cost-effective multi-agent operating group (scout, warden, treasurer, archivist, merchant) with budget policy and ledger. See [docs/agent-ops.md](docs/agent-ops.md).

## Agent ID Cards & Machine Identity

`x402-mcp` implements the **Agent-to-Agent (A2A) Protocol v1.0** and MCP machine identity for autonomous discovery.

1. **HTTP:** `GET https://x402-mcp.onrender.com/.well-known/agent-card.json` (legacy: `/.well-known/agent.json`)
2. **MCP tool:** `get_agent_card` (optional `target_id` for a skill)
3. **MCP resource:** `x402://agent-card`
4. **Registry:** `/.well-known/agents.json` · **payTo:** `/.well-known/funding.json`

Every tool accepts optional `agent_id` for per-caller quota isolation (free tier 500 calls/mo, 10/min).

## MCP Prompts Reference (4 Prompts)

Structured prompts for LLM orchestrators:

- `onboarding_flow` — first-run path: doctor → free sample → paid check
- `x402_tool_selector` — pick buyer/seller/commerce tools for a goal
- `generate_quote` — build seller payment requirements / price quote
- `troubleshoot_payment` — diagnose 402 / facilitator / signature failures

## MCP Resources Reference (4 Resources)

- `x402://agent-card` — full A2A Agent Card JSON
- `x402://server-card` — MCP server card (transport + x402 auth)
- `x402://tools-manifest` — live tool inventory
- `x402://pricing-table` — paid HTTP resources and prices

## Sample AI Agent Queries & Interactions

### Real Estate Compliance Workflow

1. `city.list` → pick a city code  
2. `city.sample` free sample for quality  
3. `city.check` or `GET /us/{code}/property-check?address=…` with x402 payment  

### Base Network Gas & Settlement Timing

- `pulse.base` free briefing  
- Paid `GET /base/tx-decision?urgency=flexible` before submit  

### Service Discovery & Protected API Consumption

- `x402.discover` → `x402.probe` → `x402.pay_and_fetch`  

### Seller API Monetization

- `x402.build_seller` with Bazaar discovery metadata → settle inbound via facilitator  

## Docker

```bash
docker build -f deployment/Dockerfile -t x402-mcp .
docker run -p 8402:8402 x402-mcp
```

## Drive Project Folder

Target: `/Forge/MCP_Projects/x402-micropayments/`

```
code/          → this repository
tests/         → pytest suite
docs/          → architecture.md
screenshots/   → verification images
manifests/     → cursor-mcp.json, /.well-known/mcp
deployment/    → Dockerfile
```

## License

Apache-2.0 compatible with x402 Foundation ecosystem.
