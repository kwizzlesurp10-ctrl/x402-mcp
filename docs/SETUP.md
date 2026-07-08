# x402 MCP — User Setup Guide

Get the x402 Micropayments MCP server running, connect it to Cursor or Grok, route profits to **your wallet**, and verify everything with tests that pass cleanly (wallet-related failures only where documented).

---

## What this server does

| Layer | What it is | How you earn |
|-------|------------|--------------|
| **MCP tools** | 10 tools agents call from Cursor/Grok | Pro upgrades and tool-credit purchases settle to your wallet |
| **x402 micropayments** | HTTP `402 Payment Required` + USDC on Base | Per-request API fees settle to `X402_PAY_TO_ADDRESS` |
| **Microservice** | FastAPI HTTP server on port 8402 | Publish paid endpoints agents discover in the x402 Bazaar |

You configure **one recipient wallet** (`X402_PAY_TO_ADDRESS`) to collect seller revenue, Pro tier payments, and tool-credit purchases. Buyers use their own `EVM_PRIVATE_KEY` only when calling `pay_and_fetch`.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | Check with `python --version` |
| Git | Optional — clone or use the project folder |
| EVM wallet address | Your profit destination (MetaMask, Coinbase Wallet, etc.) |
| Testnet funds (optional) | Base Sepolia ETH + USDC for live `pay_and_fetch` demos |

**Recommended testnet:** Base Sepolia (`eip155:84532`). Fund via the [CDP Faucet](https://docs.cdp.coinbase.com/faucets/introduction/quickstart).

---

## Step 1 — Install (about 2 minutes)

### Windows (PowerShell)

```powershell
cd C:\Users\Keith\x402-mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

### macOS / Linux

```bash
cd x402-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

## Step 2 — Point profits to your wallet

Open `.env` and set your **recipient address**. Every on-chain payment the server collects (API micropayments, Pro upgrades, tool credits) routes here.

```env
# Your wallet — where profits land
X402_PAY_TO_ADDRESS=0xYourWalletAddressHere

# Testnet facilitator (free, no API key)
X402_FACILITATOR_URL=https://x402.org/facilitator
X402_DEFAULT_NETWORK=eip155:84532
X402_DEFAULT_PRICE=$0.01

# Public URL when running HTTP mode (update for production)
PUBLIC_BASE_URL=http://localhost:8402
UPGRADE_URL=https://your-site.example.com/upgrade
```

| Variable | Required for | What happens without it |
|----------|--------------|-------------------------|
| `X402_PAY_TO_ADDRESS` | Seller tools, Pro tier, tool credits | Those tools return a clear `ValueError` — **expected** until you set it |
| `EVM_PRIVATE_KEY` | `pay_and_fetch` only | Buyer tool returns `EVM_PRIVATE_KEY required` — **expected** if you are not spending USDC |

**Security:** Never commit `.env`. Private keys stay on your machine; tool responses never echo them.

---

## Step 3 — Optional buyer wallet (pay for external APIs)

Only needed if agents should **spend** USDC via `pay_and_fetch`:

```env
EVM_PRIVATE_KEY=0xYourBuyerPrivateKey
```

Use a **separate** hot wallet with limited testnet USDC — not your main profit wallet.

---

## Step 4 — Connect to Cursor (local MCP)

1. Edit `manifests/cursor-mcp.json` — set the path to your `run_stdio.py`:

```json
{
  "mcpServers": {
    "x402-micropayments": {
      "command": "python",
      "args": ["C:\\Users\\Keith\\x402-mcp\\run_stdio.py"],
      "env": {
        "X402_PAY_TO_ADDRESS": "0xYourWalletAddressHere",
        "X402_FACILITATOR_URL": "https://x402.org/facilitator"
      }
    }
  }
}
```

2. In Cursor: **Settings → MCP → Add server** (paste the JSON block).
3. Restart Cursor. You should see **10 tools** under `x402-micropayments`.

**Smoke test in Cursor:** Ask the agent to call `get_supported_networks`. You should get protocol `v2`, network list, and a `meta` block with `quota_remaining`.

---

## Step 5 — Run as HTTP microservice

For remote connectors (Grok HTTP/SSE) or Docker:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8402
```

Verify:

```powershell
curl http://localhost:8402/health
curl http://localhost:8402/.well-known/mcp
```

`/health` should include `x402-micropayments-mcp`. The manifest should list all **10 tools**.

### Docker

```powershell
docker build -f deployment/Dockerfile -t x402-mcp .
docker run -p 8402:8402 --env-file .env x402-mcp
```

Pass `X402_PAY_TO_ADDRESS` via `--env-file .env` so the container can build seller payment requirements.

---

## Step 6 — Monetization flows (profits to your wallet)

### A. Sell API access (x402 micropayments)

1. Set `X402_PAY_TO_ADDRESS` to your wallet.
2. Call `build_seller_requirements` — returns a `PAYMENT-REQUIRED` payload with `pay_to` = your address.
3. Attach that payload to your HTTP route (return `402` with x402 headers).
4. Agents call `verify_payment_payload` after buyers pay; USDC settles on-chain to you.

### B. Pro tier (MCP subscription)

1. Set `X402_PAY_TO_ADDRESS`.
2. Agent calls `get_pro_upgrade_requirements` → payment instructions ($29 default).
3. Buyer pays on-chain; agent calls `activate_pro_tier` with the payment proof.
4. Revenue settles to your wallet; agent gets 50,000 calls/month.

### C. Per-use tool credits

1. Set `X402_PAY_TO_ADDRESS`.
2. `get_tool_credits_requirements` → per-pack price ($1 / 100 credits default).
3. `purchase_tool_credits` after payment → credits added; revenue to your wallet.

### D. List in Bazaar (discovery)

Publish your paid HTTP base URL so agents find you:

```
discover_services → your endpoint appears in x402 Bazaar results
```

Set `PUBLIC_BASE_URL` to your deployed host before going live.

---

## Step 7 — Test without surprises

### Full test suite (should be all green)

```powershell
.\.venv\Scripts\python -m pytest -v
```

Expect **49+ passed** on a fresh install. Warnings about `httpx` / `websockets` are harmless.

### Quick health checks

```powershell
# HTTP manifest lists 10 tools
curl http://localhost:8402/.well-known/mcp

# Goal verification script (writes evidence logs)
.\.venv\Scripts\python scripts\verify_goal.py
```

### Expected errors (not bugs)

These are **normal** when wallet env vars are unset:

| Tool | Expected error |
|------|----------------|
| `pay_and_fetch` | `EVM_PRIVATE_KEY` required |
| `build_seller_requirements` | `pay_to address required` |
| `get_pro_upgrade_requirements` | `X402_PAY_TO_ADDRESS required` |
| `get_tool_credits_requirements` | `X402_PAY_TO_ADDRESS required` |

Set the env vars in Step 2–3 to clear them.

### Optional live testnet flow

After funding a buyer wallet on Base Sepolia:

1. `discover_services` — find a paid endpoint
2. `get_payment_requirements` — confirm `402` + payment headers
3. `pay_and_fetch` — auto-pay and fetch the resource

Network or facilitator outages may cause skips in `test_discover_services_structure` — that is expected in CI without network.

---

## Environment reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8402` | HTTP port |
| `X402_PAY_TO_ADDRESS` | — | **Your profit wallet** |
| `EVM_PRIVATE_KEY` | — | Buyer spend wallet |
| `X402_FACILITATOR_URL` | `https://x402.org/facilitator` | Payment verifier |
| `X402_DEFAULT_NETWORK` | `eip155:84532` | Base Sepolia testnet |
| `X402_DEFAULT_PRICE` | `$0.01` | Default per-call price |
| `FREE_TIER_MONTHLY_QUOTA` | `500` | Free MCP calls/month |
| `FREE_TIER_RATE_LIMIT_PER_MIN` | `10` | Free rate limit |
| `UPGRADE_URL` | — | Pro upgrade landing page |
| `PUBLIC_BASE_URL` | `http://localhost:8402` | Manifest base URL |
| `REDIS_URL` | — | Optional quota store |

### Production (mainnet)

```env
X402_FACILITATOR_URL=https://api.cdp.coinbase.com/platform/v2/x402
X402_DEFAULT_NETWORK=eip155:8453
CDP_API_KEY_ID=your_key
CDP_API_KEY_SECRET=your_secret
```

Use your real mainnet wallet in `X402_PAY_TO_ADDRESS` only after testnet validation.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| MCP tools missing in Cursor | Check `run_stdio.py` path in MCP config; restart Cursor |
| `pay_and_fetch` fails immediately | Set `EVM_PRIVATE_KEY`; fund wallet with Sepolia ETH + USDC |
| Seller tools fail | Set `X402_PAY_TO_ADDRESS` |
| `429 rate_limit_exceeded` | Free tier: 10 calls/min — wait or upgrade to Pro |
| `quota_exceeded` | 500 calls/month on free tier — use `upgrade_url` |
| Docker `/health` unreachable | `docker run -p 8402:8402` and wait ~5s for uvicorn |

---

## Next steps

- [Architecture](architecture.md) — system diagram and tool inventory
- [Runbook](runbook.md) — operations, Redis migration, Drive artifacts
- [README](../README.md) — tool table and commerce meta envelope