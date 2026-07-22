# x402-mcp — A User's Guide

**x402-mcp** is one Python service that lets an AI agent pay for HTTP APIs, and lets you charge
for your own — over the same protocol, settling real USDC on Base. It is a FastAPI app and an
MCP server sharing one codebase, one config, and one ledger.

By the end of this guide you will have it running locally, understand both halves (paying and
getting paid), know how to connect it to an MCP client, and be able to deploy it publicly
without losing money to the two mistakes that are easy to make: putting a spend key on a public
box, and running a storefront whose books do not survive a restart.

Every command here was checked against the code in this repository. Where something could not be
verified, it was removed rather than guessed at.

---

## Contents

- [What x402-mcp Is](#what-x402-mcp-is)
- [Quickstart](#quickstart)
- [Buying: paying for someone else's endpoint](#buying-paying-for-someone-elses-endpoint)
- [Selling: charging for your own endpoint](#selling-charging-for-your-own-endpoint)
- [MCP tools](#mcp-tools)
- [Deploying it publicly](#deploying-it-publicly)
- [Operate and troubleshoot](#operate-and-troubleshoot)

---

## What x402-mcp Is

x402-mcp is a single Python service that lets an AI agent **pay for HTTP APIs** and lets you **charge for your own** — over the same protocol, with real USDC on Base. It ships as a FastAPI app (`app/main.py`) and an MCP server (`app/mcp_server.py`) sharing one codebase, one config, and one ledger.

### x402 in one paragraph

HTTP has always had a status code nobody used: `402 Payment Required`. x402 finally gives it a meaning. A client requests a protected URL, gets back a `402` whose body carries machine-readable payment terms (amount, asset, recipient, network), signs a stablecoin transfer, and retries the same request with a payment header. A *facilitator* verifies the signature and settles it on-chain; the server then returns the real response plus a receipt header. No accounts, no API keys, no invoices, no minimum charge — a request can cost a cent. This repo speaks x402 v2 end to end and settles USDC on Base mainnet (`eip155:8453`) through the Coinbase CDP facilitator.

### MCP in one paragraph

The Model Context Protocol is how an AI client (Cursor, Claude, a custom agent) discovers and calls tools on a server. Connect this server and the model gets 16 tools — the canonical list lives in `app/tools_registry.py`, which also generates the `/.well-known/mcp` manifest. That means "pay this endpoint" becomes something the model can decide to do mid-task, not something you hand-code into a client.

### The buyer side

Your agent needs data it doesn't have. `discover_services` queries the x402 Bazaar catalog for paid HTTP APIs. `get_payment_requirements` probes any URL and reports what a `402` would demand. `pay_and_fetch` signs, pays, and returns the content — with `max_price_usdc` as a hard cap, so a resource that asks for more is refused rather than paid. Every payment is recorded to `ledger/spend.jsonl`, and `ledger/policy.json` holds the spend caps enforced before money moves.

The buyer side needs a funded wallet (`EVM_PRIVATE_KEY`). That is exactly why the public storefront at <https://x402-mcp.onrender.com> does not have one.

### The seller side

The same server sells. `build_seller_requirements` mints the `402` challenge for your own endpoint; `verify_payment_payload` checks a buyer's payload with the facilitator. Two first-party endpoints are live as worked examples: `GET /mn/property-check?address=...` at $0.01 (a Minneapolis rental-compliance snapshot composed from live city open data) and `GET /swarm/products/{id}/purchase` at $0.25 (Base Network Pulse — settlement-conditions intelligence computed from real RPC and spot data). All sales settle to `X402_PAY_TO_ADDRESS`; the seller host never holds a spend key.

Above both sides sits a commerce overlay (`app/commerce.py`): free tier at 500 calls/month and 10/min, a pro tier and per-use credits purchasable over x402 or Stripe, and a `meta` envelope on every tool response reporting quota. `app/swarm/` closes the loop — it buys cheap upstream services, composes a priced composite, and lists it for resale.

### Who this is for

Developers who want an agent to transact without a billing relationship, and developers who want to sell data to agents that will never sign up for an account. If you only want one half, you can run only one half: omit the spend key and you have a storefront; skip `X402_PAY_TO_ADDRESS` and you have a buyer.

One thing worth knowing before you sell anything: **the CDP Bazaar catalog indexes a resource when it is settled, not when it is published.** A brand-new paid endpoint is invisible to discovery until someone pays it once. `scripts/settle_once.py` exists for that — for a self-owned resource, the money moves between your own wallets.

---

## Quickstart

Goal: a locally running x402 storefront in under ten minutes, ending with a real `402 Payment Required` challenge you generated yourself. No wallet funds, no Coinbase account, no Redis needed for this part.

### What you're starting

One FastAPI process (`app/main.py`) that is simultaneously an MCP server (16 tools, see `app/tools_registry.py`) and an HTTP storefront with x402-gated endpoints. There is also a React "Mission Control" dashboard in `dashboard/` — **skip it for now**. See [The light path vs. the heavy path](#the-light-path-vs-the-heavy-path) below.

### 1. Clone and create the venv

Python 3.11+ is required (`pyproject.toml`: `requires-python = ">=3.11"`; CI runs 3.12).

Windows (PowerShell):

```powershell
git clone <REPO_URL> x402-mcp
cd x402-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

macOS / Linux:

```bash
git clone <REPO_URL> x402-mcp
cd x402-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Install takes a couple of minutes — `requirements.txt` pulls `x402[httpx,evm,svm,fastapi]`, `eth-account`, and `solana>=0.36,<0.40` (that upper pin is deliberate: x402's Solana signer imports a sync client that solana 0.40 removed).

Throughout this guide, `PY` means the venv interpreter: `.venv\Scripts\python.exe` on Windows, `.venv/bin/python` elsewhere. The `Makefile` and `scripts/dev_up.py` both hardcode the Windows path, so on macOS/Linux run the underlying commands directly rather than `make`.

### 2. The minimum .env

`.env.example` lists every knob; for a first local run you only need one line to be non-empty. Open `.env` and set:

```env
X402_PAY_TO_ADDRESS=<YOUR_WALLET>
```

That is your **receive** address — every x402 sale settles there. It can be any EVM address you control; nothing is spent by setting it. Leave the rest of `.env.example` as shipped. In particular:

- `X402_DEFAULT_NETWORK=eip155:84532` (Base Sepolia) and `X402_FACILITATOR_URL=https://x402.org/facilitator` are the free, no-API-key testnet defaults. Base mainnet (`eip155:8453`) needs Coinbase CDP credentials — that's a later section.
- `EVM_PRIVATE_KEY` stays **empty**. It is the buyer/spend key, only needed by `pay_and_fetch`. Never put it on a host that serves the public.
- `REDIS_URL` stays commented out. Without it, quota is in-memory and ledgers/listings are files under `ledger/` — fine on your laptop, lossy on an ephemeral host.

All of these are read by `app/config.py` (pydantic-settings), which loads `.env` automatically. Field names map to env vars uppercased: `mn_property_check_price` ← `MN_PROPERTY_CHECK_PRICE`, and so on.

### 3. Start the API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8402
```

macOS / Linux:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8402
```

On Windows there is a shortcut for exactly this line:

```powershell
make api
```

Run it from the repo root — `app/config.py` resolves `.env` relative to the working directory.

### 4. Prove it works

Three requests, in increasing order of interest.

**Is it alive?**

```bash
curl http://127.0.0.1:8402/health
```

```json
{"status":"ok","service":"x402-micropayments-mcp","x402_facilitator":"https://x402.org/facilitator",
 "wallet_configured":false,"stripe_configured":false,"pay_to_configured":true}
```

`pay_to_configured: true` confirms your `.env` was picked up. `wallet_configured` refers to the *buyer* key and should be `false` — that's correct for a seller-only setup.

**Does it announce itself as an MCP server?**

```bash
curl http://127.0.0.1:8402/.well-known/mcp
```

You get the manifest built from `app/tools_registry.py`, listing all 16 tools and the `stdio` / `streamable-http` / `sse` transports.

**The one that actually proves x402 works** — hit a paid endpoint with no payment attached:

```bash
curl -i "http://127.0.0.1:8402/mn/property-check?address=1700%20Penn%20Ave%20N"
```

You should get **HTTP 402** with a `PAYMENT-REQUIRED` response header (the x402 v2 wire format) and a JSON body naming the price, the resource URL, and the network:

```json
{"error":"payment_required","resource":"...","price":"$0.01","network":"eip155:84532",
 "how_to_pay":"Retry with PAYMENT-SIGNATURE header (x402 v2); requirements are in the PAYMENT-REQUIRED response header."}
```

That 402 *is* the product. A paying agent reads the `PAYMENT-REQUIRED` header, signs a USDC transfer authorization, and retries with a `PAYMENT-SIGNATURE` header; the server then verifies and settles through the facilitator before serving the report.

If you get **503 `seller_not_configured`** instead of 402, `X402_PAY_TO_ADDRESS` is still unset — the route refuses to sell on behalf of nobody.

**Bonus:** open <http://127.0.0.1:8402/dashboard> in a browser. That route is the single-file, zero-build operator dashboard baked into `app/dashboard.py` — it is not the Vite app, and it costs you nothing to open.

### 5. Have the doctor check your setup

```powershell
.\.venv\Scripts\python.exe -m app.doctor
```

Same checks as `GET /doctor`, printed as a readable report and exiting non-zero if anything failed. On a fresh local install expect `pass` on `.env present`, `Receive wallet`, `Default network`, and `Facilitator reachable`, plus `warn` on the three persistence checks (in-memory quota, file ledgers, file registry). Those warnings are the expected local state — they become real problems only when you deploy to a host with no disk, which is what `REDIS_URL` is for.

### The light path vs. the heavy path

The README's `make up` runs `scripts/dev_up.py`, which starts **two** processes: uvicorn on 8402 *and* `pnpm dev` (Vite + React 19) in `dashboard/` on 5173. That path additionally requires Node and pnpm, an `npm`-scale `pnpm install` in `dashboard/`, and a Vite dev server that keeps a file watcher and a TypeScript/HMR pipeline resident. On a memory-constrained machine it is by far the most expensive thing in this repo.

For everything in this quickstart — and for most day-to-day work on the payment paths — **start only the API**. `make api` / the bare `uvicorn` line above is the light path, and `/dashboard` already gives you live health, quota meters, and revenue panels with no build step. Reach for `make up` only when you are actually changing the React dashboard source.

### Run the tests (optional, ~1 minute)

The Python suite is hermetic — it spins up a local mock facilitator, so no internet and no funds are required:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

One gotcha worth knowing before you panic: on a machine with a *fully configured* `.env` and populated `ledger/*.jsonl`, roughly four tests fail locally that pass in CI — the "missing wallet" tests in `test_mcp_tools.py` / `test_x402_services.py` and `test_ops.py::test_ledger_spend_empty`. They assert the unconfigured behaviour. `make test` also runs the dashboard's vitest suite via pnpm; skip it if you never installed the dashboard.

### Where to go next

- Connect it to Cursor over stdio: `python run_stdio.py`, using `manifests/cursor-mcp.json` as the config template.
- Selling for real on Base mainnet: you need `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET`, `SWARM_SELL_NETWORK=eip155:8453`, and `REDIS_URL`. There is also a non-obvious discovery quirk — the CDP Bazaar catalog indexes a resource when a payment for it **settles**, not when you publish it, so a brand-new paid endpoint is invisible until someone pays it once. `scripts/settle_once.py` exists for that.

---

## Buying: paying for someone else's endpoint

The buyer side is what lets an agent spend money without you in the loop. That is genuinely useful and genuinely dangerous, so this half of the repo is built around one idea: **every payment passes through a single chokepoint with a hard cap in front of it.**

### The one secret that matters

`EVM_PRIVATE_KEY` is the spend key. It is the only thing here that can move funds, and it is required by exactly one tool, `pay_and_fetch`.

Keep it on a machine you control. Never put it on a host that serves the public — a seller box needs no spend key at all, because buyers sign their own transfers and the facilitator settles to your `X402_PAY_TO_ADDRESS`. The quickest audit is `curl <host>/health`: `wallet_configured` must be `false` on anything public.

Fund that wallet with USDC on the network you intend to buy on. On Base mainnet (`eip155:8453`) settlement is gasless for the buyer — payments use EIP-3009 transfer authorizations, so you sign a message rather than sending a transaction, and you do not need ETH for gas.

### Finding something to buy

```bash
curl -s "http://127.0.0.1:8402/health"   # confirm the server is up first
```

Three tools cover discovery, in increasing order of commitment:

- **`discover_services`** queries the CDP Bazaar catalog for paid HTTP services. Takes `query`, `limit` (max 100) and `max_price_usdc`. The catalog is large, so filter.
- **`get_payment_requirements`** probes any URL and decodes what its `402` would demand — price, network, asset, recipient. It spends nothing and needs no wallet, so it is safe to point at anything.
- **`pay_and_fetch`** actually pays.

You can run the probe from a shell without an MCP client at all:

```bash
.venv/Scripts/python -c "import asyncio,json;from app.models import GetPaymentRequirementsInput as I;from app import x402_services as x;print(json.dumps(asyncio.run(x.get_payment_requirements(I(url='https://x402-mcp.onrender.com/mn/property-check?address=1700 Penn Ave N'))),indent=2))"
```

### Paying, with the brakes on

`pay_and_fetch` takes `url`, `method`, `headers`, `body`, `preferred_network` and — the important one — **`max_price_usdc`**.

That cap is not advisory. If every payment option a resource advertises costs more than the cap, the request is refused before anything is signed. Set it on every call. An agent that decides mid-task to buy something is only as safe as the ceiling you gave it.

Underneath sits a second layer you do not have to remember to use: the **warden**, in `app/swarm/policy.py`, which reads `ledger/policy.json` and vets purchases against running totals derived from the spend ledger. The shipped defaults are deliberately small:

```json
{
  "max_price_per_call_usdc": 0.05,
  "daily_cap_usdc": 0.50,
  "monthly_cap_usdc": 3.00,
  "allowed_networks_mainnet": ["eip155:8453"],
  "testnet_networks": ["eip155:84532"]
}
```

Raise them when you mean to, not when a purchase gets refused. `domain_allowlist` and `domain_denylist` are there too if you want to constrain *where* an agent may spend, not just how much.

### A one-shot purchase from the command line

`scripts/settle_once.py` is the simplest possible buyer: one resource, one hard cap, one row in the ledger.

```bash
.venv/Scripts/python scripts/settle_once.py --url https://<host>/some-resource --max-usdc 0.01
```

```bash
.venv/Scripts/python scripts/settle_once.py --url https://<host>/search \
    --method POST --body '{"query": "x402"}' --max-usdc 0.01
```

Flags: `--url` and `--max-usdc` are required; `--method` (default `GET`), `--body`, `--content-type`, `--network` (default `eip155:8453`) and `--label` are optional. It prints the status code, whether it settled, and the transaction hash.

Two properties worth internalising, because they define how you should treat failures:

1. **Nothing is recorded unless settlement actually succeeded on-chain.** Verification passing is not enough — the script checks `payment_settled` before writing anything.
2. **A failed attempt moves no funds.** The CDP facilitator returns transient `502`s often enough that you will meet one. There is no automatic retry anywhere in the repo, and there is nothing to reconcile afterwards: just run it again.

### Where the money went

Every settled purchase appends a row to the spend ledger, readable at `GET /ledger/spend` or on disk at `ledger/spend.jsonl` when Redis is not configured:

```json
{"ts":"...","kind":"spend","agent_id":"settle-a1b2c3d4","network":"eip155:8453",
 "amount_usdc":0.01,"amount_usdc_atomic":10000,"tx":"0x...","settled":true,"url":"https://..."}
```

`amount_usdc_atomic` is the integer form (USDC has 6 decimals) and is what the aggregates net on. `GET /swarm/revenue` folds spend and revenue together into realized margin and LTV:CAC — and counts only rows where `settled` is truthy, so a failed attempt can never inflate your reported spend.

### Which networks actually work

Base mainnet (`eip155:8453`) and Base Sepolia (`eip155:84532`), for the `exact` scheme.

The split that catches people out is **which facilitator settles which network**. The free `https://x402.org/facilitator` handles Base Sepolia only. Base mainnet requires Coinbase CDP credentials (`CDP_API_KEY_ID` / `CDP_API_KEY_SECRET`), and `CDP_NETWORKS` decides which networks get routed there. Buying on mainnet without CDP creds fails at verify, not at signing — so it looks like a resource problem when it is really a config problem.

Ask the server what it supports rather than guessing:

```bash
curl -s http://127.0.0.1:8402/probe?url=<resource-url>
```

or call the `get_supported_networks` tool, which returns the protocol version, the network list and the v2 header names in one response.

---

## Selling: charging for your own endpoint

The seller side of x402 is small: when a request arrives without payment you answer **HTTP 402** with a `PAYMENT-REQUIRED` header, and when the caller retries with a `PAYMENT-SIGNATURE` header you verify + settle it and serve the goods. This repo wraps both halves so you only write the "serve the goods" part.

### What a seller needs (and what it must not have)

A seller only needs a receive address and facilitator credentials:

| Variable | Why |
| --- | --- |
| `X402_PAY_TO_ADDRESS` | Where every sale settles. Without it `build_seller_requirements` raises. |
| `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` | Coinbase CDP facilitator creds — required to verify+settle on Base **mainnet**. The free `https://x402.org/facilitator` only settles Base Sepolia. |
| `CDP_NETWORKS` (default `eip155:8453`) | Which CAIP-2 networks get routed to CDP instead of the free facilitator (`app/x402_services.py::_use_cdp`). |
| `PUBLIC_BASE_URL` | Your public origin. It is baked into the resource URL that ends up in the discovery catalog, so a wrong value publishes a dead link. |

It does **not** need `EVM_PRIVATE_KEY`. That is the buyer-side spend key; `docs/SELLER-STOREFRONT.md` is blunt about it — a public storefront holding it is exposing a funded wallet. Check with `curl https://<your-host>/health` and confirm `wallet_configured` is `false`. The server signs nothing on-chain; the facilitator moves the buyer's USDC to `X402_PAY_TO_ADDRESS`.

### build_seller_requirements: the one call that makes a 402

`app/x402_services.py::build_seller_requirements` is the single place a challenge is built. Everything else — the MN compliance endpoint, the pro-tier upgrade, tool credits, the swarm's composite listings — routes through it. It returns a dict whose important key is `payment_required_header`: a ready-to-serve, base64 x402 v2 challenge you hand to the buyer verbatim.

You can reach it three ways:

- the MCP tool `build_seller_requirements` (params: `network`, `pay_to`, `price`, `scheme`, `description`, `resource_url`, `mime_type`, `discoverable`, `discovery_method`, `discovery_input_example`, `discovery_output_example`)
- `POST /seller/requirements` — keyless, but gated behind `DASHBOARD_ACTIONS=true` (403 otherwise), and it only forwards `network`/`pay_to`/`price`/`scheme`/`description`, not the discovery fields
- directly in Python, which is what your own endpoint should do

Only `scheme="exact"` is supported; anything else is rejected up front rather than blowing up inside the SDK.

### Wiring it into an endpoint

`app/mn_compliance.py` + the `/mn/property-check` handler in `app/main.py` are the reference implementation of a paid endpoint. The shape:

```python
payment_required = mn_compliance.build_payment_required_header()   # base64 challenge
signature = request.headers.get("PAYMENT-SIGNATURE")
if not signature:
    return JSONResponse(status_code=402,
                        headers={"PAYMENT-REQUIRED": payment_required},
                        content={"error": "payment_required", ...})

result = await mn_compliance.verify_and_settle(signature, payment_required)
if not result["is_valid"] or not result["payment_settled"]:
    return JSONResponse(status_code=402, headers={"PAYMENT-REQUIRED": payment_required}, ...)

report = await mn_compliance.check_property(address)   # deliver only after settle
return JSONResponse(content=report, headers={"PAYMENT-RESPONSE": receipt})
```

Two details worth copying. First, gate on `payment_settled`, not just `is_valid` — verification passing only means the signature was well-formed; `SettleResponse.success` is what proves funds moved. Second, the `PAYMENT-RESPONSE` header carries the settlement receipt back to the buyer; the composite purchase endpoint additionally sets `Access-Control-Expose-Headers: PAYMENT-REQUIRED,PAYMENT-RESPONSE` so browser clients can read them.

Try the unpaid half against the live storefront:

```bash
curl -i "https://x402-mcp.onrender.com/mn/property-check?address=1700%20Penn%20Ave%20N"
# HTTP/1.1 402  +  PAYMENT-REQUIRED: <base64>
```

Decode that header with the buyer-side probe (no wallet needed) to see exactly what you published:

```bash
.venv/Scripts/python -c "import asyncio,json;from app.models import GetPaymentRequirementsInput as I;from app import x402_services as x;print(json.dumps(asyncio.run(x.get_payment_requirements(I(url='https://x402-mcp.onrender.com/mn/property-check?address=1700 Penn Ave N'))),indent=2))"
```

### Pricing

Prices are plain dollar strings (`"$0.01"`), configured per product in `app/config.py`:

| Setting | Default | Sells |
| --- | --- | --- |
| `X402_DEFAULT_PRICE` | `$0.01` | fallback price |
| `MN_PROPERTY_CHECK_PRICE` | `$0.01` | `/mn/property-check` |
| `PULSE_PRICE` | `$0.25` | `/swarm/products/{id}/purchase` |
| `PRO_TIER_PRICE` | `$29.00` | MCP pro tier |
| `TOOL_CREDIT_PACK_PRICE` | `$1.00` | 100 tool credits |

Network choice matters as much as the number. `SWARM_SELL_NETWORK` decides where composites list. For the commerce paths, `resolve_revenue_network()` picks `REVENUE_NETWORK` if set, else the first entry in `CDP_NETWORKS` when CDP creds exist, else `X402_DEFAULT_NETWORK` — deliberately, so a mainnet-credentialed deploy can't hand out real quota for free Sepolia USDC just because the default network is Sepolia.

One non-obvious constraint: **descriptions are clamped to 500 characters** (`CDP_MAX_DESCRIPTION_CHARS`). The CDP facilitator rejects both verify *and* settle above that, so a long description silently breaks revenue, not just discovery. The clamp is central and logs a warning when it fires.

### Bazaar discoverability

Passing `resource_url` is what turns a private 402 into a catalogable one. When it is set, `build_seller_requirements` attaches:

- **`ResourceInfo`** — `url`, `description`, `mime_type`, plus `service_name` from `BAZAAR_SERVICE_NAME` and tags from `BAZAAR_SERVICE_TAGS`. Facilitator-side limits are enforced here: name ≤ 32 chars, ≤ 5 tags of ≤ 32 chars each. Violations are silently dropped, so overlong tags just vanish.
- **`extensions.bazaar`** — an `{"info": ..., "schema": ...}` block describing how to call you: the HTTP method, example query params (GET/HEAD/DELETE) or JSON body (POST/PUT/PATCH), and an example response. Set `BAZAAR_DISCOVERABLE=false`, or pass `discoverable=False`, to opt out per-call.

Buyer clients copy `extensions` verbatim into the signed payload, and the facilitator reads it at settle time. There's a repo-specific fix baked in: the SDK's `declare_discovery_extension` omits the HTTP method, and without it `info` fails validation against its own `schema` and the facilitator catalogs *nothing* — so `_build_discovery_extension` injects the method explicitly. Give real examples; `mn_compliance.DISCOVERY_INPUT_EXAMPLE` / `DISCOVERY_OUTPUT_EXAMPLE` show the intended size (small but faithful excerpts of the actual response).

For the swarm's composite listings, `app/swarm/models.py::purchase_discovery_metadata` builds those three fields from the product id and `PUBLIC_BASE_URL`, producing `{base}/swarm/products/{product_id}/purchase`.

### The catch: CDP catalogs on SETTLE, not on publish

This is the part that surprises everyone. Publishing a 402 with perfect Bazaar metadata puts you in **no** catalog. The CDP discovery index adds a resource when a payment against it **settles**. Until someone pays you once, you are invisible — and nobody can discover you in order to pay you.

You break the loop by paying yourself. `scripts/settle_once.py` exists for exactly this: a one-shot purchase with a hard price cap, routed through the same sole spender (`pay_and_fetch`), so a resource asking for more than the cap is refused rather than paid. For a self-owned resource the money moves between your own wallets.

```bash
.venv/Scripts/python scripts/settle_once.py --url https://<your-host>/mn/property-check?address=1700%20Penn%20Ave%20N --max-usdc 0.01
```

```bash
.venv/Scripts/python scripts/settle_once.py --url https://<your-host>/search --method POST \
    --body '{"query": "x402"}' --max-usdc 0.01
```

Flags: `--url`, `--max-usdc` (both required), `--method` (default `GET`), `--body`, `--content-type`, `--network` (default `eip155:8453`), `--label`. It prints `settled=` and the tx hash, and writes a spend row **only** if settlement actually succeeded.

Run this from a machine that *does* have a buyer `EVM_PRIVATE_KEY` — not from the seller storefront, which by design has none.

Expect to retry. The CDP facilitator returns transient 502s often enough to matter; that path moves no funds and records nothing, so re-running is safe. The script says so itself: *"no funds moved, nothing recorded. Transient 502s retry fine."*

### Keep the cataloged URL alive

Once the catalog has indexed `.../swarm/products/{id}/purchase`, that URL must keep resolving. On an ephemeral host a restart wipes `ledger/products.json`, the registry comes back empty, and every buyer who discovered you gets a 404 against a listing that still looks live in the Bazaar.

Two defenses, both in the repo:

- Set `REDIS_URL` (Upstash) so the swarm registry, quota, and ledgers survive restarts. Without it the file store is used, and an ephemeral filesystem loses everything.
- Set `PINNED_PULSE_PRODUCT_ID` to a fixed hex id. `app/swarm/publisher.py::restore_pinned_listing` runs at startup and republishes onto that same id, so the indexed URL keeps resolving. `PINNED_PULSE_MAX_AGE_SECONDS` (default 900) forces a refresh of a restored report rather than selling a frozen snapshot as "live"; accumulated `revenue_usdc` is carried across the rebuild. If the republish fails, boot continues — a broken listing must never take down `/health`.

Related honesty detail worth imitating: the published Pulse description deliberately omits the block height, because catalogs index a description once and never revisit it, while the listing itself is rebuilt with fresh data. Volatile facts belong in the delivered report, not in the cataloged description.

### Check your work

```bash
.venv/Scripts/python -m app.doctor        # PASS/WARN/FAIL over config, facilitator + discovery reachability
curl https://<your-host>/doctor            # same checks over HTTP
curl https://<your-host>/ledger/revenue    # settled sales, newest first
```

---

## MCP tools

This server is a FastMCP server wrapped in a FastAPI app. Everything an agent can do is exposed as an MCP tool, and every tool call goes through one chokepoint (`_execute_tool` in `app/mcp_server.py`) that meters quota, attaches a commerce `meta` envelope to the response, and emits an ops event. There is no way to call a tool and skip billing.

### Start with the manifest

The server publishes a machine-readable manifest at `/.well-known/mcp` (built by `app/manifest.py`). It is the fastest way to see what a given deployment actually offers — tool list, tiers, quota numbers, x402 headers, and the endpoint map.

```bash
curl https://x402-mcp.onrender.com/.well-known/mcp
# or, locally:
curl http://localhost:8402/.well-known/mcp
```

The manifest declares `"transport": ["stdio", "streamable-http", "sse"]` and `capabilities: {tools: true, resources: false, prompts: false}` — this server is tools-only.

### Connecting over stdio (recommended for local clients)

`run_stdio.py` is a four-line launcher that runs the same `mcp` object over stdio:

```bash
python run_stdio.py
```

A ready-made client config lives at `manifests/cursor-mcp.json`:

```json
{
  "mcpServers": {
    "x402-micropayments": {
      "command": "python",
      "args": ["${workspaceFolder}/run_stdio.py"],
      "env": {
        "EVM_PRIVATE_KEY": "${EVM_PRIVATE_KEY}",
        "X402_PAY_TO_ADDRESS": "${X402_PAY_TO_ADDRESS}",
        "X402_FACILITATOR_URL": "https://x402.org/facilitator",
        "UPGRADE_URL": "https://forge.example.com/upgrade"
      }
    }
  }
}
```

On Windows point `command` at the venv interpreter (`.venv\Scripts\python.exe`) rather than bare `python`, so the client picks up the project's dependencies. Only set `EVM_PRIVATE_KEY` on a machine you intend to spend from — it is the buyer key, and the public storefront deliberately runs without it.

Smoke test after connecting: ask the agent to call `get_supported_networks`. You should get protocol `v2`, a network list, and a `meta` block with `quota_remaining`.

### Connecting over HTTP

Run the FastAPI app and the MCP Streamable HTTP transport is mounted alongside the REST endpoints:

```bash
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8402
# or: make api
```

`app/main.py` mounts the transport with `app.mount("/mcp", _mcp_http_app)`, and the FastMCP sub-app serves Streamable HTTP at its own `/mcp` path — so the JSON-RPC endpoint is `http://localhost:8402/mcp/mcp`. If the installed SDK has no `streamable_http_app()`, the code falls back to `mcp.sse_app()` at the same mount point. The manifest separately advertises `connector_url` as `${PUBLIC_BASE_URL}/mcp/sse`, so set `PUBLIC_BASE_URL` in production and treat the manifest's `connector_url` as the value your connector UI should be given.

One caveat worth knowing before you debug it yourself: POSTing to `/mcp/mcp` on the public Render host returns `Invalid Host header` — the MCP SDK's DNS-rebinding protection rejects the forwarded host. Local stdio and local HTTP work fine; remote HTTP connector use against the public host is not currently working end to end.

### The tools

All 16 tools are declared in `app/tools_registry.py`, which is the single source of truth feeding the manifest, the README, and the guard tests. Every tool is `tier: "free"` — meaning it is included in the metered free tier rather than gated behind Pro. Some need environment variables to do anything useful; those are listed as `requires_env` in the manifest.

Every tool also accepts an optional `agent_id` argument. Pass a stable one — if you omit it, `resolve_agent_id` mints a fresh UUID per call, so your quota, tier and purchased credits will not accumulate against a single identity.

| Tool | What it does | Tier | Requires |
|---|---|---|---|
| `discover_services` | Discover x402 Bazaar paid HTTP services | free | — |
| `get_payment_requirements` | Probe a URL for HTTP 402 payment requirements | free | — |
| `pay_and_fetch` | Pay via x402 and fetch a protected resource | free | `EVM_PRIVATE_KEY` |
| `build_seller_requirements` | Build seller-side x402 payment requirements (optionally with the Bazaar discovery extension) | free | `X402_PAY_TO_ADDRESS` |
| `verify_payment_payload` | Verify a payment signature via the facilitator | free | — |
| `get_supported_networks` | List networks, facilitators, and v2 headers | free | — |
| `get_pro_upgrade_requirements` | Build x402 payment requirements for a Pro tier upgrade | free | `X402_PAY_TO_ADDRESS` |
| `activate_pro_tier` | Verify an x402 payment and unlock Pro tier quota | free | — |
| `get_tool_credits_requirements` | Build x402 payment requirements for per-use tool credits | free | `X402_PAY_TO_ADDRESS` |
| `purchase_tool_credits` | Verify an x402 payment and add per-use tool credits | free | — |
| `create_stripe_checkout` | Create a Stripe Checkout Session for Pro tier or tool credits (fiat rail) | free | `STRIPE_SECRET_KEY` |
| `run_swarm_research` | Run the swarm Agency: buy cheap upstream x402 services, compose a composite report, list it for resale | free | `EVM_PRIVATE_KEY`, `X402_PAY_TO_ADDRESS` |
| `settle_composite_sale` | Verify + settle a buyer's payment for a listed composite and record the revenue | free | — |
| `swarm_revenue_report` | Portfolio revenue intelligence: spend, revenue, LTV:CAC, margins, per-source profit scores | free | — |
| `get_base_pulse` | Live Base Network Pulse — base fee, utilization, USD settlement cost, settle-now/hold verdict from real RPC data | free | — |
| `get_os_metrics` | Host OS telemetry: CPU, memory, swap, disk, network, process signals with an ok/warn/critical verdict | free | — |

Useful non-obvious arguments (from `app/mcp_server.py`): `discover_services` takes `query`, `limit`, `max_price_usdc`; `pay_and_fetch` takes `preferred_network` and `max_price_usdc` as a spend ceiling; `build_seller_requirements` takes `resource_url` plus `discovery_method` / `discovery_input_example` / `discovery_output_example` to embed the Bazaar discovery extension; `get_base_pulse` takes `depth`; `get_os_metrics` takes `include_processes`.

### What comes back

Tools return JSON strings shaped as `{"data": ..., "meta": ...}`. The `meta` envelope (`app/models.py::ResponseMeta`) always carries `tier`, `calls_this_month`, `quota_remaining`, `quota_warning` (true at ≥80% consumption), `rate_limit_remaining`, and `tool_credits_remaining`.

Quota is enforced *before* the tool body runs. Free tier defaults are 500 calls/month and 10 calls/minute; Pro is 50,000/month. When you are over quota the call returns `{"error": ..., "data": null, "meta": null}` instead of raising — check for `error` before reading `data`. Purchased tool credits are consumed only once the monthly quota is exhausted.

### Adding a tool

If you extend the server, the registry is load-bearing. Per `CLAUDE.md`, a new tool must touch `app/mcp_server.py`, `app/tools_registry.py`, the README count and table, `tests/test_readme.py`, and `tests/test_assessor.py`; `tests/test_manifest.py` and `tests/test_mcp_tools.py` derive from the registry automatically. Verify with:

```bash
.venv/Scripts/python -m pytest tests/test_manifest.py tests/test_mcp_tools.py -q
```

---

## Deploying it publicly

This is a normal FastAPI app in a container, so hosting it is easy. What is *not* obvious is that a public box here is a **seller**: it takes money, it never spends it, and its state (who paid, what is listed, what has been earned) has to outlive a restart or the money you already took becomes unaccounted for. Almost every deploy rule below exists for one of those two reasons.

### Two Dockerfiles, and which one you want

There are two, and they differ in exactly one way:

- `Dockerfile` (repo root) — `CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8402}`. Shell form, so it honours a `$PORT` injected by the platform at runtime. This is the one PaaS hosts (Render, Heroku-likes) need.
- `deployment/Dockerfile` — identical build, but `EXPOSE 8402` and a hardcoded `--port 8402`. Use this where *you* pick the port: local Docker, `docker-compose.yml`, and Fly (`fly.toml` sets `dockerfile = "deployment/Dockerfile"` with `internal_port = 8402`).

Both are `python:3.12-slim`, install `requirements.txt`, and copy only `app/`, `run_stdio.py` and `manifests/`. No `.env` is ever copied into the image — secrets arrive as runtime env vars.

Local smoke test before you deploy anything:

```bash
docker build -f deployment/Dockerfile -t x402-mcp .
docker run -p 8402:8402 x402-mcp
```

There's also a scripted version that builds, runs the container twice and probes `/health` plus the MCP manifest:

```bash
.venv/Scripts/python scripts/verify_docker.py
```

### render.yaml

`render.yaml` is a Render Blueprint for a `runtime: docker`, `plan: free`, `region: oregon` web service built from the **root** Dockerfile. Every secret in it is marked `sync: false` — meaning Render will not read it from git, you type it into the dashboard. Everything else (networks, Bazaar metadata, posture flags) is committed as plain `value:` entries, because they're configuration, not secrets.

Two things about the free plan matter operationally: it spins down after ~15 minutes idle, and **it has no persistent disk**. The first one means you should publish your listing and run the discovery settle while the box is warm. The second one is the reason for the next two sections.

### The environment variables that matter

Everything is read through `app/config.py` (pydantic-settings, so `X402_PAY_TO_ADDRESS` maps to `x402_pay_to_address`, etc.). These are the ones a public deploy actually turns on:

| Variable | What breaks without it |
| --- | --- |
| `X402_PAY_TO_ADDRESS` | Nothing gets sold. `/doctor` FAILs the `pay_to` check, `/mn/property-check` returns `503 seller_not_configured`, and pro-tier/credit challenges raise. This is your USDC receive address. |
| `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` | You can't verify or settle on Base mainnet. The free `x402.org` facilitator only settles `exact` on Base Sepolia — mainnet needs the Coinbase CDP facilitator. Also, with no CDP creds, `resolve_revenue_network()` falls back to the testnet default. |
| `REDIS_URL` | See below. Non-optional on a diskless host. |
| `OPERATOR_TOKEN` | `/quota/{agent_id}` is left **open** to the world (`app/main.py`: the bearer check only runs `if settings.operator_token`). Set it. The dashboard injects it into its own JS so operator polls still work. |
| `PUBLIC_BASE_URL` | Discovery metadata catalogs the *wrong* URL. It is what builds `purchase_url` in `POST /pulse/publish` and `resource_url()` for `/mn/property-check`. If it still says `http://localhost:8402`, buyers who find you in the Bazaar cannot reach you — and `/doctor` treats a localhost value as "this is dev" and stops enforcing the mainnet check. |
| `CDP_NETWORKS`, `REVENUE_NETWORK`, `X402_DEFAULT_NETWORK`, `SWARM_SELL_NETWORK` | Network incoherence. Details below. |
| `BAZAAR_DISCOVERABLE`, `BAZAAR_SERVICE_NAME`, `BAZAAR_SERVICE_TAGS` | Your 402 challenges go out without the Bazaar discovery extension, so a settled payment doesn't catalog you. Facilitator limits: name ≤ 32 printable ASCII chars, ≤ 5 tags of ≤ 32 chars each — violations are silently dropped. |
| `PINNED_PULSE_PRODUCT_ID` | Every boot mints a fresh uuid, so the purchase URL already indexed in the Bazaar 404s after any restart. Setting a hex id makes the lifespan in `app/main.py` call `publisher.restore_pinned_listing()` (45s timeout, non-fatal) so the same URL comes back. `PINNED_PULSE_MAX_AGE_SECONDS` (default 900) forces a rebuild of a stale restored report rather than selling one boot's Pulse forever. |
| `SWARM_ENABLED` | Leave it `false` on a public box. `true` turns on the buyer role, which a seller-only deploy must not have. |
| `DASHBOARD_ACTIONS` | `false` makes the app read-only: CORS drops to `GET` only and `POST /pulse/publish` returns `403 DASHBOARD_ACTIONS is disabled; publishing is off.` Keep it `true` if you need the manual republish escape hatch; the deploy plan's original sequence was to flip it off after the first publish. |
| `SWARM_PRODUCTS_FILE` | Where the file-backed listing snapshot goes (default `ledger/products.json`); setting it to an empty string disables file persistence entirely. Only relevant when you don't have Redis. |

### Why REDIS_URL is required, not optional

Three separate stores need to survive a restart: the quota store (`app/commerce.py`), the spend/revenue ledgers (`app/ledger_store.py`), and the swarm registry that holds your listings and their per-product revenue (`app/swarm/registry.py`). All three share one connection built in `app/redis_client.py`.

That module is deliberately non-fatal: if `REDIS_URL` is set but unreachable, it logs, records a `fallback_reason`, and lets everything degrade to memory/files. A storefront still serving 402s beats one that is down — but on a host with no disk, "files" means `/app/ledger/*` inside a container that is thrown away on the next deploy or idle spin-down. You would lose paid entitlements (a buyer who paid for Pro tier is back to free), the record that a sale ever happened, and the listing behind your cataloged purchase URL.

So `app/doctor.py` is loud about it. It probes the **live store object**, not the env var, because `REDIS_URL` being set proves nothing if startup fell back:

- No `REDIS_URL` at all → three `warn`s ("In-memory quota store — resets on restart", etc.).
- `REDIS_URL` set but the store is in memory / on files → **`fail`**, with messages like `REDIS_URL set but the ledgers fell back to FILES (...) — settled sales will be lost on the next restart`.
- Redis live → `pass` on all three, and `/doctor`'s `config.redis_mode` reads `redis`.

Any managed Redis works (Upstash is what the plan assumes; free tier is plenty — quota state for a handful of agents is a few hundred keys). Note the client uses `socket_connect_timeout=2.0`, so an `rediss://` URL that needs TLS and a slow handshake can silently fall back — check `/doctor` after every deploy, not just the first.

### Seller-only: never put the spend key on a public box

This is the one rule with no exceptions. `EVM_PRIVATE_KEY` / `SVM_PRIVATE_KEY` are **buyer** secrets — they're what `pay_and_fetch` spends from. Selling needs none of it: a buyer signs, the CDP facilitator verifies and settles to `X402_PAY_TO_ADDRESS`. A public box carrying a spend key is a funded wallet on the internet.

The repo enforces this in several places, and you should keep all of them:

- `render.yaml` has no key entry, with a comment saying never to add one.
- `deployment/seller.env.example` carries everything a storefront needs and explicitly refuses the key.
- `deployment/set_fly_secrets.sh` forwards an explicit allow-list (`X402_PAY_TO_ADDRESS CDP_API_KEY_ID CDP_API_KEY_SECRET`) and hard-refuses with exit 2 if a denied key ever appears in the payload.

Your post-deploy proof is one curl:

```bash
curl -s https://<your-app>/health
```

`wallet_configured` must be **`false`**. (`/doctor` will show a `warn` on "Vault key (optional) — EVM_PRIVATE_KEY not set — paying disabled". On a seller box that warning is the correct state, not a problem to fix.)

The buyer side lives on your operator machine, which is also where the discovery settle runs from:

```bash
.venv/Scripts/python scripts/settle_once.py --url https://<your-app>/swarm/products/<product_id>/purchase --max-usdc 0.25
```

That's the CDP Bazaar quirk in action: a paid endpoint is indexed when it is **settled**, not when it is published, so it stays invisible until someone pays it once. `--max-usdc` is a hard cap, and nothing is written to the ledger unless the payment actually settled on chain — so the transient CDP 502s are safe to just retry.

### Network coherence (mainnet vs testnet)

The default in `app/config.py` is `X402_DEFAULT_NETWORK=eip155:84532` (Base Sepolia) and `SWARM_SELL_NETWORK=eip155:84532`. That is right for local dev and wrong for anything public — you would be handing out real Pro-tier quota in exchange for free testnet USDC.

`app/doctor.py` will not let that ship. `resolve_revenue_network()` picks explicit `REVENUE_NETWORK` first, else the first entry of `CDP_NETWORKS` when CDP creds are set, else the testnet default. The doctor then **fails** the deploy if you have a pay-to address, `PUBLIC_BASE_URL` is not localhost, and the resolved revenue network is a testnet:

```
[FAIL] Revenue network: Public deploy would sell pro tier/credits on testnet eip155:84532
       fix: Set REVENUE_NETWORK=eip155:8453 (or configure CDP creds)
```

Set all four, as `render.yaml` does, because they govern different code paths:

```
CDP_NETWORKS=eip155:8453          # which networks route to the CDP facilitator
REVENUE_NETWORK=eip155:8453       # pro tier / tool credit challenges
X402_DEFAULT_NETWORK=eip155:8453  # the /mn/property-check 402 is built on this
SWARM_SELL_NETWORK=eip155:8453    # what Pulse/composite listings are priced on
```

`SWARM_SELL_NETWORK` is the one people forget: the config default is testnet, and it's what a published listing is sold on. `X402_DEFAULT_NETWORK` is the other: `/mn/property-check` builds its `PAYMENT-REQUIRED` header from it directly, so leaving it at Sepolia gives you a mainnet storefront with one testnet product on it.

### Deploy checklist

1. Provision Redis, get an `rediss://` URL.
2. Set the secrets in your host's dashboard/secret store: `X402_PAY_TO_ADDRESS`, `CDP_API_KEY_ID`, `CDP_API_KEY_SECRET`, `OPERATOR_TOKEN`, `REDIS_URL`. Never a private key.
3. Deploy (Render picks up `render.yaml`; on Fly, `fly deploy` from the repo root plus `bash deployment/set_fly_secrets.sh`).
4. Confirm `PUBLIC_BASE_URL` matches the URL the host actually assigned you.
5. `curl https://<your-app>/health` → `wallet_configured: false`.
6. `curl https://<your-app>/doctor` → `summary.ready: true`, `config.redis_mode: "redis"`, revenue network `eip155:8453`, zero fails.
7. `POST /pulse/publish` (needs `DASHBOARD_ACTIONS=true`), capture the `purchase_url`.
8. From the operator machine, run `scripts/settle_once.py` against that URL once to trigger Bazaar indexing. The catalog refresh is on the order of hours, so check again later rather than immediately.

You can run the same checks locally before you push — the doctor is also a CLI:

```bash
.venv/Scripts/python -m app.doctor
```

It exits 0 when ready and 1 when any check fails, so it drops straight into a pre-deploy gate.

---

## Operate and troubleshoot

Two surfaces do almost all the operating work: `/doctor` (machine-readable health checks) and `/dashboard` (the live operator terminal). Everything below is read-only — you can hit it on the public storefront without touching money.

### `/doctor` — is this box actually able to sell?

```bash
curl -s https://x402-mcp.onrender.com/doctor | python -m json.tool
```

Locally you can run the same checks as a CLI, which prints `[PASS]/[WARN]/[FAIL]` plus a `fix:` line for anything not passing:

```bash
.venv/Scripts/python -m app.doctor        # Windows venv; exits 1 if any check FAILs
```

Both call `run_checks()` in `app/doctor.py`, so they agree — but the CLI reads *your local* `.env` and *your local* stores. To judge a deployed box, use the HTTP endpoint on that box.

The response is `{"checks": [...], "summary": {...}, "config": {...}}`. `summary.ready` is `true` only when zero checks are `fail`. The checks, and what each one is really telling you:

| id | Meaning when it's not green |
| --- | --- |
| `env_file` | WARN — no `.env`, running on defaults only. Fine in a container where config comes from the environment. |
| `pay_to` | FAIL — `X402_PAY_TO_ADDRESS` unset. You cannot collect anything; paid routes like `/mn/property-check` answer **503 `seller_not_configured`**. |
| `buyer_key` | WARN — `EVM_PRIVATE_KEY` unset, so `pay_and_fetch` is disabled. On the public storefront this WARN is **correct and desired**: it is the proof that the seller box holds no spend key. |
| `redis` | Persistence of quota/entitlements. See the failure table below. |
| `ledger` | Persistence of the settled spend/revenue ledgers. |
| `registry` | Persistence of listings and per-product revenue (`app/swarm/registry.py`). |
| `facilitator` | Pings `{X402_FACILITATOR_URL}/supported`. Anything `< 500` counts as reachable. FAIL means you cannot verify or settle at all. |
| `discovery` | Pings `CDP_DISCOVERY_URL`. Only ever WARN — discovery may legitimately require auth. |
| `mcp_json` | FAIL when an agent definition under `.claude/agents/` references an `mcp__<name>__` server that `.mcp.json` doesn't define. SKIP when neither file exists (normal on a deployed box). |
| `network` | Informational: `X402_DEFAULT_NETWORK`. |
| `revenue_network` | FAIL when a non-localhost `PUBLIC_BASE_URL` would sell pro tier / tool credits on Base Sepolia (`eip155:84532`). Free testnet USDC buying real quota is the bug this check exists to prevent. Fix: `REVENUE_NETWORK=eip155:8453`. |

The three persistence checks are deliberately paranoid. They probe the **live store object**, not the env var — `REDIS_URL` being set proves nothing if startup already fell back. That is why `redis` inspects `commerce.quota_store.mode` and calls `store.ping()`, and why `ledger` and `registry` fall to FAIL (not WARN) when `settings.redis_url` is set but the store landed on memory/files.

### `/dashboard` — the operator terminal

`GET /dashboard` (and `/`, which 307-redirects there) serves a single self-contained HTML page from `app/dashboard.py`. No build step, no external state. Panels:

- **Service health** — polls `/health` every 5s, with a latency sparkline. `wallet key: not configured (probe-only)` is the seller-only posture; the header lamp goes red and the board dims when a poll fails.
- **Agent quota** — reads `/quota/<agent_id>` without consuming a call. If `OPERATOR_TOKEN` is set, the page injects it so its own polls authenticate; a bare `curl` to `/quota/...` without `Authorization: Bearer <token>` gets **401**.
- **Tool matrix** — the tool list straight from `/.well-known/mcp`, with each tool's `requires_env` tags painted green/red from the live `/health` config flags. A red `env` tag means that tool will error if called.
- **Revenue paths** — pro tier, tool credits, free tier, read from the manifest and `/upgrade`.
- **Storefront** — the money panel. It fans out to `/swarm/products`, `/swarm/revenue` and `/ledger/revenue`, and shows realized revenue, upstream spend, `N listed · M sold`, a listings table (topic / price / earned), and the last 8 settled sales with truncated tx hashes. Note the cadence: health and quota poll every 5s, the storefront every **30s**, and it is skipped entirely while the tab is hidden — those three endpoints read Redis, and a tab left open all day at 5s would eat a real share of a free plan's monthly command budget.
- **Event tape** — pauses while you hover it so you can read or copy a line, then flushes what it buffered.

If the Storefront panel says `nothing listed` or `no settled sales yet` on a box you know has sold something, that is not a UI bug — go read the persistence section below.

### The ledgers

Two append-only ledgers, exposed newest-first (max 1000 rows) at `GET /ledger/spend` and `GET /ledger/revenue`:

```bash
curl -s https://x402-mcp.onrender.com/ledger/revenue | python -m json.tool
curl -s https://x402-mcp.onrender.com/swarm/revenue  | python -m json.tool
```

Rows carry `ts`, `kind`, `agent_id`, `network`, `amount_usdc`, `amount_usdc_atomic` (integer, 6 decimals), `tx` and `settled`. Only rows with `settled` truthy are counted by `/swarm/revenue`, so a failed payment attempt can never inflate reported spend, revenue or margin.

Backing store is chosen once at import (`app/ledger_store.py`): `REDIS_URL` set and reachable → Redis lists (trimmed to 50,000 rows each); otherwise the git-ignored `ledger/spend.jsonl` and `ledger/revenue.jsonl`. Files are the local-dev default. Never commit or casually reset these — they are the only local record that a real sale happened.

### Failure modes you will actually hit

| Symptom | What's going on | What to do |
| --- | --- | --- |
| Facilitator returns **502** mid-settle; `payment_settled` is false | The CDP facilitator throws transient 502s often enough to matter. This path is safe: no funds move and nothing is written to the ledger (`scripts/settle_once.py` returns 1 and prints `no funds moved, nothing recorded`). | Just run it again. Do not "reconcile" anything — there is nothing to reconcile. |
| `/doctor` FAILs `redis` / `ledger` / `registry` with *"REDIS_URL set but running IN-MEMORY / fell back to FILES"* | `app/redis_client.py` tried once at import, the PING failed, and every store silently fell back. The message includes the recorded `fallback_reason` (e.g. `ConnectionError: ...`). Serving continues on purpose — a storefront that still answers 402s beats one that is down — but the next restart eats your entitlements, ledgers and listings. | Fix the URL/credentials or Redis availability, then **restart the process**. The client is built at import; nothing re-tries on its own. |
| After a restart on an ephemeral host: `/swarm/products` is empty and the cataloged purchase URL answers **404** | Render's free plan restarts and comes back with an empty filesystem, so file-backed listings vanish while the money is still on-chain. This already cost real records once. | Set `REDIS_URL`. As a belt-and-braces measure, set `PINNED_PULSE_PRODUCT_ID` — `restore_pinned_listing()` in `app/swarm/publisher.py` runs at startup and republishes a fresh Pulse onto the *same* product id (carrying its accumulated `revenue_usdc` across), so the URL already sitting in the catalog stays resolvable. It also refreshes a listing whose report has aged past `PINNED_PULSE_MAX_AGE_SECONDS`. |
| A paid endpoint is live and correct but never shows up in the CDP Bazaar catalog | The catalog indexes a resource when it is **settled**, not when it is published. Until someone pays it once, it is invisible — a pure chicken-and-egg. | Settle it yourself once. `scripts/settle_once.py` exists for exactly this and pays through the sole spender with a hard cap: `.venv/Scripts/python scripts/settle_once.py --url https://<your-host>/swarm/products/<id>/purchase --max-usdc 0.25`. Run it from a machine that holds the spend key, never from the seller box. Record it as a self-purchase; never present it as external revenue. Expect ~6h for the catalog to refresh. |
| `GET /mn/property-check` returns **422**, not 402 | `address` is a *required* query parameter. FastAPI rejects the request before any payment logic runs. The handler also returns 422 `invalid_address` for an empty or >120-char address. | Send the parameter: `curl -i "https://x402-mcp.onrender.com/mn/property-check?address=<street+address>"`. A well-formed request with no `PAYMENT-SIGNATURE` header gives **402** plus a `PAYMENT-REQUIRED` header — that's the healthy answer. |
| **402** with `"error": "payment_invalid"` instead of 200 | Verify or settle came back bad. `invalid_reason` and `settlement_error` are in the body. | Read those two fields. A transient facilitator error here is the same 502 story — retry. |
| `/swarm/products/{id}/purchase` returns **404** or **409** | 404 = unknown `product_id` (usually the lost-listing case above). 409 = the product exists but has no `payment_required_header`, i.e. it was never actually listed for sale. | Republish the listing. |
| POST to `/pulse/publish`, `/swarm/run` or `/seller/requirements` returns **403** | `DASHBOARD_ACTIONS` is false — the dashboard is read-only by design, and these routes move real funds or mutate listings. | Set `DASHBOARD_ACTIONS=true`, do the one operation, then flip it back and redeploy. |

### A sensible daily check

```bash
curl -s https://x402-mcp.onrender.com/health
curl -s https://x402-mcp.onrender.com/doctor  | python -c "import sys,json; d=json.load(sys.stdin); print(d['summary']); [print(c['status'].upper(), c['name'], '-', c['message']) for c in d['checks'] if c['status']!='pass']"
curl -s https://x402-mcp.onrender.com/swarm/revenue
```

Green means: `summary.ready` true, `/health` showing `wallet_configured: false` on the seller box, and `/swarm/revenue` totals that match what you expect the ledgers to hold.
---

## Where to get help

Three places, in the order worth trying:

1. **`/doctor`** — run it first, always. `curl <host>/doctor` on a deployed box, or
   `.venv/Scripts/python -m app.doctor` locally. It names the broken thing and prints a `fix:`
   line for it, and it exits non-zero when anything failed, so it also works as a pre-deploy gate.
2. **`/dashboard`** — the single-file operator terminal. Live health, quota, the tool matrix, and
   the Storefront panel showing listings, earnings and settled sales. No build step; just open it.
3. **The tests** — the suite is hermetic (a local mock facilitator, no funds and no network
   needed), so it doubles as executable documentation of intended behaviour. When you want to
   know what something really does, `tests/` usually answers faster than reading the code:

   ```bash
   .venv/Scripts/python -m pytest -q
   ```

If a paid endpoint of yours is behaving strangely, the fastest triage is almost always to ask it
for its own `402` and read what it actually published:

```bash
curl -i "https://<your-host>/<your-resource>"
```
