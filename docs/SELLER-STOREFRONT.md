# Base Network Pulse — Seller Storefront

Deploy guide for running a **public, seller-only** storefront that sells the
**Base Network Pulse** product: live Base settlement intelligence synthesized
from real RPC data, the Coinbase ETH spot price, and EIP-1559 math.

This deployment **sells only**. It publishes the Pulse as a payable x402
product, serves the HTTP 402 challenge, and settles paid sales to your receive
address. It never buys anything.

---

## Security property: no spend key

The seller path — **publish → serve 402 → settle** — needs only:

- `X402_PAY_TO_ADDRESS` — where sales settle (your Base mainnet address)
- `CDP_API_KEY_ID` + `CDP_API_KEY_SECRET` — Coinbase CDP facilitator creds that
  verify and settle x402 payments on Base mainnet

It **never** needs `EVM_PRIVATE_KEY`. That variable is a **buyer-only** spend
key used to *pay* for services. A public storefront that holds it is exposing a
funded wallet to the internet.

> **Do not put `EVM_PRIVATE_KEY` in your seller environment.** If
> `wallet_configured` shows `true` on `/health`, a spend key leaked in — stop
> and remove it.

Settlement is custodial-free from the storefront's side: the CDP facilitator
moves the buyer's USDC to `X402_PAY_TO_ADDRESS`. The server signs nothing
on-chain and holds no funds.

---

## Configure

Copy the template and fill it in:

```bash
cp deployment/seller.env.example seller.env
# edit seller.env: set X402_PAY_TO_ADDRESS, CDP_API_KEY_ID, CDP_API_KEY_SECRET,
# and PUBLIC_BASE_URL to your public host.
```

| Variable | Purpose |
| --- | --- |
| `X402_PAY_TO_ADDRESS` | Your Base mainnet receive address; all sales settle here |
| `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` | Coinbase CDP facilitator creds (verify + settle) |
| `CDP_NETWORKS=eip155:8453` | Route Base mainnet settlement through CDP |
| `SWARM_SELL_NETWORK=eip155:8453` | List the Pulse product on Base mainnet |
| `DASHBOARD_ACTIONS=true` | Allow `POST /pulse/publish` (read-only if false) |
| `PUBLIC_BASE_URL` | Public origin; used to build the purchase URL |
| `PULSE_PRICE=$8.00` | List price per synthesized Pulse report |

**Do not** add `EVM_PRIVATE_KEY`.

---

## Run seller-only

### Docker

```bash
docker build -t x402-pulse -f deployment/Dockerfile .
docker run --env-file seller.env -p 8402:8402 x402-pulse
```

### Docker Compose

```bash
docker compose -f deployment/docker-compose.seller.yml up -d
```

### Uvicorn (bare metal)

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8402 --env-file seller.env
```

> Run from a directory without a repo `.env`, or the app will also read that
> file and may pick up variables you did not intend (including a buyer key).
> Confirm with `curl localhost:8402/health` → `"wallet_configured": false`.

---

## Expose publicly

The server listens on `localhost:8402`. Put a public origin in front of it.

### Option A — Cloudflare Tunnel (quick, no static IP)

```bash
cloudflared tunnel --url http://localhost:8402
```

Cloudflare prints a public `https://…trycloudflare.com` URL. Set that as
`PUBLIC_BASE_URL` and restart so published purchase URLs point at it. Good for
demos; use a named tunnel + custom hostname for anything long-lived.

### Option B — Static-IP VPS

Run the container on a VPS with a fixed public IP behind TLS (Caddy/nginx). A
**static IP also fixes CDP IP-allowlist churn**: the Coinbase CDP facilitator
can be allowlisted to a stable egress IP, so settlement calls don't break each
time a dynamic address rotates. Preferred for production.

Either way, point `PUBLIC_BASE_URL` at the public origin so the purchase URL in
`POST /pulse/publish` is reachable by buyers.

---

## Endpoints buyers use

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/pulse` | Free live preview of the current Base Network Pulse |
| `POST` | `/pulse/publish` | Mint a listing; returns `product_id`, `price_usdc`, `pay_to`, `purchase_url` (gated by `DASHBOARD_ACTIONS`) |
| `GET`/`POST` | `/swarm/products/{id}/purchase` | Pay for the report; 402-gated |
| `GET` | `/health` | Liveness + `wallet_configured` (must be `false` for a seller) |

**Buyer flow:**

1. `GET /pulse` — preview the intelligence for free.
2. `POST /pulse/publish` — mint a fresh listing. Returns a `product_id` and a
   `purchase_url`.
3. `GET {purchase_url}` with no `PAYMENT-SIGNATURE` → **HTTP 402** with a
   `PAYMENT-REQUIRED` header (the x402 challenge: price, network, `pay_to`).
4. Buyer pays via x402 and retries with a `PAYMENT-SIGNATURE` header. The CDP
   facilitator verifies and settles the USDC to `X402_PAY_TO_ADDRESS`, and the
   report is delivered with a `PAYMENT-RESPONSE` settlement header.

---

## Pricing

Set by `PULSE_PRICE` (default `$8.00`). It becomes the listed `price_usdc` and
the amount encoded in the 402 `PAYMENT-REQUIRED` challenge. Change it and
restart; each new `POST /pulse/publish` mints a listing at the current price.
