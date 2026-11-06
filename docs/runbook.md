# x402 MCP Runbook

> **New users:** start with [SETUP.md](SETUP.md) for step-by-step install, wallet/profit config, and testing.

## Local Development (stdio)

```powershell
cd path\to\x402-mcp
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Edit .env: EVM_PRIVATE_KEY, X402_PAY_TO_ADDRESS as needed
python run_stdio.py
```

### Cursor MCP Config

Copy `manifests/cursor-mcp.json` entries into Cursor MCP settings.

## HTTP / Grok Connector

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8402
```

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness |
| `GET /.well-known/mcp` | Connector manifest + tier info |
| `GET /upgrade` | Stripe + x402/Coinbase payment rails |
| `POST /stripe/checkout` | Create Stripe Checkout Session |
| `POST /stripe/webhook` | Stripe webhook (signature verified) |
| `GET /mcp/sse` | MCP SSE transport (when mounted) |

Set `PUBLIC_BASE_URL` for production connector URL in manifest.

## Environment Variables

See `.env.example`. Critical:

- `STRIPE_SECRET_KEY` — primary fiat rail (Stripe Checkout)
- `STRIPE_WEBHOOK_SECRET` — verify `POST /stripe/webhook` signatures
- `EVM_PRIVATE_KEY` — buyer wallet for `pay_and_fetch` (x402 alternate rail)
- `X402_PAY_TO_ADDRESS` — seller recipient for x402 revenue tools (future/alternate)
- `X402_FACILITATOR_URL` — testnet: `https://x402.org/facilitator`
- `REDIS_URL` — optional; swap in Redis quota store when scaling. When set, **MCP commerce** (`commerce.activate_pro` / `commerce.purchase_credits`) uses the same Redis for **cross-worker settlement coordination** (`mcp_settle:*` keys: result cache, attempt state, token locks). No extra connection string beyond this env.
- `MCP_COMMERCE_REDIS_STRICT` — default `true`. When `REDIS_URL` is set, MCP commerce **fails closed** (payment rejected, no on-chain retry in that request) if Redis is unreachable at session start, if lock acquisition hits a Redis I/O error, or if the client is nil after a failed ping. Set `false` only for intentional **single-process / dev** use where cross-worker duplicate settlement is acceptable; it is not silent degradation in production—document the tradeoff before toggling.

### MCP commerce settlement guarantees (Redis + facilitator)

| Guarantee | When |
|-----------|------|
| Same payment + same server-issued challenge → at most one successful settle recorded in Redis | `REDIS_URL` set, Redis healthy, `MCP_COMMERCE_REDIS_STRICT=true` |
| Cached result cannot authorize a different challenge | Result blobs carry `challenge_fp`; reads require a match |
| Lock safety | Random token; release uses compare-and-delete (wrong token does not delete) |
| Contention | Loser waits (async poll); timeout → `settlement_contention_timeout`; ambiguous peer state → `settlement_ambiguous_manual_reconciliation` |
| Verify/settle exception after success unclear | `ambiguous_settlement` attempt record; response `settlement_exception_ambiguous` (no automatic repeat settle in-process) |

**Facilitator-dependent gaps:** If the facilitator accepts a settlement but the process crashes before Redis records success, or Redis is lost mid-flight after `settle_payment` returned, on-chain state may not match server idempotency—**manual reconciliation** (ledger / chain) remains the source of truth for “was USDC actually moved?”. This server does not auto-retry ambiguous outcomes.

**Dev / no Redis:** With `REDIS_URL` unset, idempotency is **in-process only** (single worker); do not rely on it across replicas.

**Dev / strict off:** `MCP_COMMERCE_REDIS_STRICT=false` with `REDIS_URL` set uses Redis when the client connects but does **not** fail closed on unreachable Redis; suitable only when you accept that multi-worker safety is not enforced.

### A2A JSON-RPC (`POST /a2a`)

Task ownership is enforced with a **capability token** returned on each new task as `capabilityToken`. Clients must send it on `tasks/get`, `tasks/cancel`, and when resuming paid flows (`message/send` with payment metadata). See [A2A-TASK-CAPABILITY.md](A2A-TASK-CAPABILITY.md).

Optional header `X-A2A-Client-Id`: when sent on task creation, later calls must use the **same** id with the capability.

## Redis Migration

Replace `InMemoryQuotaStore` in `app/commerce.py`:

```python
# Keys: agent:{id}:month:{YYYY-MM}, agent:{id}:rl:{minute_bucket}
# See comments in commerce.py for migration path.
```

## Testing

```powershell
pytest -v
```

## Drive Artifact Location

Target folder: `/Forge/MCP_Projects/x402-micropayments/`

Local mirror:

```
x402-mcp/
├── code/        (app/, run_stdio.py)
├── tests/
├── docs/
├── screenshots/ (phase-0-bootstrap-my-drive.png)
├── manifests/
└── deployment/
```

Upload via `google_drive_upload_artifact` when API is connected.

## Wallet & Facilitator Setup (Live x402)

### Buyer (`pay_and_fetch`)

1. Create or import an EVM wallet (Base Sepolia testnet recommended).
2. Fund with Base Sepolia ETH (gas) + testnet USDC via [CDP Faucet](https://docs.cdp.coinbase.com/faucets/introduction/quickstart).
3. Set in `.env`:
   ```
   EVM_PRIVATE_KEY=0x...
   X402_FACILITATOR_URL=https://x402.org/facilitator
   X402_DEFAULT_NETWORK=eip155:84532
   ```
4. Invoke MCP tool `pay_and_fetch` with a discovered paid endpoint URL.

### Seller (`build_seller_requirements`, `verify_payment_payload`)

1. Set recipient wallet:
   ```
   X402_PAY_TO_ADDRESS=0x...
   X402_FACILITATOR_URL=https://x402.org/facilitator
   ```
2. `build_seller_requirements` → returns PAYMENT-REQUIRED payload for your endpoint.
3. `verify_payment_payload` → validates buyer PAYMENT-SIGNATURE via facilitator.

### Production (CDP Facilitator)

```
X402_FACILITATOR_URL=https://api.cdp.coinbase.com/platform/v2/x402
CDP_API_KEY_ID=...
CDP_API_KEY_SECRET=...
X402_DEFAULT_NETWORK=eip155:8453
```

## Profitability Path

Revenue is collected via the **commerce overlay** (MCP tool access) and **on-chain x402 settlements** (API micropayments):

| Layer | Mechanism | Revenue |
|-------|-----------|---------|
| MCP tools | Free: 500 calls/mo, 10/min; Pro tier via `upgrade_url` | Subscription / upgrade |
| Seller APIs | `build_seller_requirements` + x402 middleware on your HTTP routes | Per-request USDC via `pay_to` |

**Monetization checklist:**
1. Deploy HTTP server (`uvicorn app.main:app --port 8402`) with `PUBLIC_BASE_URL` set.
2. Publish `/.well-known/mcp` manifest (includes `tiers.pro` + `upgrade_url`).
3. Configure `X402_PAY_TO_ADDRESS` to receive on-chain micropayments.
4. Gate premium tools or higher quotas behind Pro tier at `upgrade_url`.
5. List your paid endpoints in x402 Bazaar for agent discovery.

## x402 Testnet Flow

1. Fund wallet with Base Sepolia ETH + testnet USDC (CDP faucet)
2. Set `X402_FACILITATOR_URL=https://x402.org/facilitator`
3. Set `X402_DEFAULT_NETWORK=eip155:84532`
4. `discover_services` → find a paid endpoint
5. `get_payment_requirements` → confirm 402 headers
6. `pay_and_fetch` → auto-pay and retrieve resource

## Goal Verification

```powershell
.\.venv\Scripts\python scripts\verify_goal.py
```

Evidence saved to goal scratch directory (`pytest.log`, `launch.log`, `tool_smoke.json`).
## Ops (stack / Bazaar)

See [ops-checklist.md](ops-checklist.md), [wallet-split-and-bazaar.md](wallet-split-and-bazaar.md), [seller-demo.md](seller-demo.md).
