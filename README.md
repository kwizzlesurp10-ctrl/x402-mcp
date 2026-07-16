# x402 Micropayments MCP

Production MCP server for the [x402](https://x402.org) HTTP micropayment protocol. Enables AI agents to discover paid services, probe `402 Payment Required` responses, pay with stablecoins, and build/verify seller payment configs.

## Features

- **15 MCP tools** for buyer, seller, Stripe fiat, x402 commerce, and swarm-agency flows — canonical inventory in `app/tools_registry.py` (single source for README, `/.well-known/mcp`, and tests); guarded by `tests/test_readme.py` and `tests/test_manifest.py`
- **Stripe payment rail** (primary): `create_stripe_checkout` + `POST /stripe/checkout` + `POST /stripe/webhook` for card/bank payments
- **x402/Coinbase rail** (alternate/future): crypto micropayments via facilitator and CDP discovery
- **Commerce overlay:** 500 calls/month, 10/min rate limit, `meta` envelope on every response
- **FastMCP** + **FastAPI** with `/.well-known/mcp` manifest
- **stdio** (Cursor/Grok local) and **HTTP/SSE** (remote connector) transports
- **Redis-ready** quota store (in-memory default)

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
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `discover_services` | Query x402 Bazaar for paid HTTP APIs |
| `get_payment_requirements` | Probe URL for `PAYMENT-REQUIRED` on 402 |
| `pay_and_fetch` | Auto-pay and fetch protected resource |
| `build_seller_requirements` | Build seller payment requirements |
| `verify_payment_payload` | Verify payment via facilitator |
| `get_supported_networks` | Networks, facilitators, v2 headers |
| `get_pro_upgrade_requirements` | Build x402 payment requirements for Pro tier upgrade |
| `activate_pro_tier` | Verify x402 payment and unlock Pro tier quota |
| `get_tool_credits_requirements` | Build x402 payment requirements for per-use tool credits |
| `purchase_tool_credits` | Verify x402 payment and add per-use tool credits |
| `create_stripe_checkout` | Create Stripe Checkout Session for pro tier or credits |
| `run_swarm_research` | Swarm Agency: buy cheap upstream x402 services, compose a research report, list it for resale |
| `settle_composite_sale` | Verify + settle a buyer's payment for a listed composite and record revenue |
| `swarm_revenue_report` | Portfolio revenue intelligence: spend, revenue, LTV:CAC, margins, per-source profit scores |
| `get_base_pulse` | Live Base Network Pulse: synthesized settlement-conditions intelligence (base fee, utilization, USD cost, verdict) from real RPC data |

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `STRIPE_SECRET_KEY` | For Stripe checkout | Primary fiat payment rail |
| `STRIPE_WEBHOOK_SECRET` | For `/stripe/webhook` | Webhook signature verification |
| `EVM_PRIVATE_KEY` | For `pay_and_fetch` | Buyer wallet private key (x402 alternate) |
| `X402_PAY_TO_ADDRESS` | For x402 seller tools | Recipient wallet (Coinbase/x402 future rail) |
| `X402_FACILITATOR_URL` | No | Default: `https://x402.org/facilitator` |
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