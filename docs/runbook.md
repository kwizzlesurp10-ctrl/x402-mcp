# x402 MCP Runbook

## Local Development (stdio)

```powershell
cd C:\Users\Keith\x402-mcp
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
| `GET /mcp/sse` | MCP SSE transport (when mounted) |

Set `PUBLIC_BASE_URL` for production connector URL in manifest.

## Environment Variables

See `.env.example`. Critical:

- `EVM_PRIVATE_KEY` — buyer wallet for `pay_and_fetch`
- `X402_PAY_TO_ADDRESS` — seller recipient for `build_seller_requirements`
- `X402_FACILITATOR_URL` — testnet: `https://x402.org/facilitator`
- `REDIS_URL` — optional; swap in Redis quota store when scaling

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
C:\Users\Keith\x402-mcp\
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