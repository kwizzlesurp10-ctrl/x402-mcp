# Public Storefront Deploy Plan (Bazaar indexing route)

Goal: put the seller-only storefront on a public URL, settle ONE discoverable
payment through the CDP facilitator, and get the endpoint cataloged in the
Bazaar (~6h refresh) where x402 buyer agents actually discover services.

Status of prerequisites (2026-07-16):

| Prerequisite | State |
| --- | --- |
| Revenue pipeline fixes committed | done (`1c1ef68`) |
| Pulse repriced to $0.25 | done (`7e42328`) |
| Bazaar discovery extension on 402s | done (`ec06920`) |
| RedisQuotaStore (real persistence) | done (`065b5f8`) |
| Revenue-network coherence guard | done (this commit) |
| Durable product listings | DONE — origin's `SwarmRegistry` persists listings to `ledger/products.json` (atomic snapshot, loaded at construction) + settled-tx replay guard; listings now survive restart, so the step-6 404 caveat is largely resolved (mount a persistent volume for `ledger/` on Fly so the file survives machine recreation) |

## Non-negotiables (from the swarm's enforcer)

1. **Seller-only box.** The deploy carries `X402_PAY_TO_ADDRESS` + CDP creds
   ONLY. `EVM_PRIVATE_KEY` never leaves the operator machine —
   `deployment/Dockerfile` + `seller.env.example` already enforce this and
   `/health` must show `wallet_configured: false` post-deploy.
2. **Mainnet revenue.** `/doctor` on the deployed box must show
   `revenue_network: eip155:8453` (the new coherence check FAILS the deploy if
   a public box would sell quota for testnet USDC).
3. **Do not settle the indexing payment before the listing is live and priced
   at $0.25** — the catalog's first quality snapshot bakes in what it sees.

## Provider recommendation

**Fly.io (recommended)** — shared-cpu-1x machine (~$2–3/mo, or free
allowance), native Docker (`deployment/Dockerfile` works as-is), stable
always-on process (SSE + catalog quality signals need uptime), `fly.toml` is
~15 lines. Redis via Upstash's Fly integration (free tier fits: quota state
for a handful of agents is a few hundred keys).

Alternatives considered:
- **Render** — fine, but the free tier spins down on idle (kills catalog
  quality signals and 402 latency); the paid tier ($7/mo) beats Fly on
  nothing here. Note: `origin/master` (the 17 unmerged parallel PR commits)
  contains a Render deploy config — if the branch merge happens first,
  Render becomes the path of least resistance.
- **Vercel** — hosts the dashboard (demo) well, but a long-running FastAPI
  process with SSE and in-process background state is a poor fit for
  serverless function limits. Keep Vercel for the dashboard only.
- **This host** — rejected: 7.5GB RAM at ~85%, disk ~89%; never scale locally.

## Environment matrix (deployed box)

From `deployment/seller.env.example`, plus the new knobs:

```
X402_PAY_TO_ADDRESS=0xYourReceiveAddress
CDP_API_KEY_ID=<CDP key id>
CDP_API_KEY_SECRET=<CDP secret — set via provider secret store, never in image>
CDP_NETWORKS=eip155:8453
REVENUE_NETWORK=eip155:8453          # explicit > resolved; doctor-guarded either way
PUBLIC_BASE_URL=https://<app>.fly.dev # discovery metadata catalogs THIS URL
REDIS_URL=<upstash redis url>         # doctor FAILS loudly if set-but-dead
BAZAAR_DISCOVERABLE=true
BAZAAR_SERVICE_NAME=x402 MCP Storefront
BAZAAR_SERVICE_TAGS=base,intelligence,x402,data
DASHBOARD_ACTIONS=true                # needed once for POST /pulse/publish; flip to false after
SWARM_ENABLED=false                   # no buyer role on a public box
```

## Sequence

1. Operator creates Fly app + Upstash Redis; set secrets from the matrix.
2. `fly deploy` with `deployment/Dockerfile` (add a minimal `fly.toml`,
   internal_port 8402, force_https).
3. Verify: `/health` → `wallet_configured: false`; `/doctor` → ready, redis
   mode `redis`, revenue network `eip155:8453`, no fails.
4. Publish the listing: `POST https://<app>.fly.dev/pulse/publish` → capture
   `purchase_url`, decode the served `PAYMENT-REQUIRED` header, confirm
   `extensions.bazaar` present and `resource.url` is the PUBLIC purchase URL.
5. Flip `DASHBOARD_ACTIONS=false` (redeploy) — box is read-only + payable.
6. Restart caveat (until durable listings land): any machine restart drops
   the in-memory listing → the cataloged URL 404s. Mitigation: single
   long-lived machine, republish after any deploy; PRIORITY follow-up is the
   `ledger/products.jsonl` durable-listings deliverable.
7. **The one discoverable settle** (operator machine, holds the spend key):
   `pay_and_fetch` against the public purchase URL — $0.25, Base mainnet,
   settles via CDP with the discovery extension in the payload. This is a
   self-purchase whose purpose is the catalog trigger: record it in the
   ledger as usual, never present it as external revenue.
8. Verify cataloging: poll the CDP discovery API for the purchase URL at
   +6h and +24h (`GET {cdp_discovery_url}?type=http` and search the items).
   If absent at 24h: suspect the known facilitator indexing issue, escalate
   the x402scan.com/resources/register fallback (human gate, free form).

## Cost ceiling

Fly ~$3/mo + Upstash $0 + the $0.25 indexing settle. Warden's monthly cap
($3.00) is untouched by hosting; the settle is within the operator-approved
sequence but EXCEEDS the $0.05/call warden cap if routed through the swarm —
route it as a direct operator `pay_and_fetch`, never by weakening the cap.
