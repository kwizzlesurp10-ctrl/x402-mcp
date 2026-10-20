# US City Network — agent golden path

One product, three doors: **HTTP**, **MCP tools**, **pay_and_fetch**.  
No new endpoints — packaging only ([PRODUCT-FOCUS](../PRODUCT-FOCUS.md)).

Storefront: `https://x402-mcp.onrender.com`

## Path A — pure HTTP (any agent)

```bash
BASE=https://x402-mcp.onrender.com

# 1) Free catalog
curl -sS "$BASE/us/cities" | jq '{network, price, codes: [.cities[].code]}'

# 2) Free fixed-address sample (shape check — no payment)
curl -sS "$BASE/us/mn/property-check/sample" | jq '{sample, city, next, verdict: .report.compliance_verdict}'

# 3) Paid path without signature → 402 + PAYMENT-REQUIRED
curl -sS -D- "$BASE/us/mn/property-check?address=1700%20Penn%20Ave%20N" -o /tmp/body.json | head
jq . /tmp/body.json

# 4) Pay: use an x402 client (MCP pay_and_fetch, or your wallet stack) against
#    the same URL with PAYMENT-SIGNATURE. Receipt: PAYMENT-RESPONSE header.
```

## Path B — MCP tools (Cursor / stdio / Streamable HTTP)

Manifest: `GET $BASE/.well-known/mcp` (includes city tools).

| Step | Tool | Needs wallet? |
|------|------|----------------|
| 1 | `list_us_cities` | no |
| 2 | `get_us_city_property_sample` `city_code="mn"` | no |
| 3 | `check_us_city_property` `city_code="mn"` `address="…"` | yes (`EVM_PRIVATE_KEY` on **client** host) |

Seller-only Render has **no** spend key. From a wallet-enabled MCP client:

```text
list_us_cities
get_us_city_property_sample(city_code="sea")
check_us_city_property(city_code="sea", address="<street>")
# equivalent: pay_and_fetch(url="<paid_url>?address=…")
```

Without a buyer key, step 3 returns a **402 probe + how_to_pay** (no charge).

## Path C — generic buyer tool only

```text
get_payment_requirements(url="$BASE/us/chi/property-check?address=…")
pay_and_fetch(url=same, max_price_usdc=0.05)
```

## Operator checks (local)

```bash
# Sample reliability (free, all cities)
.venv/bin/python scripts/probe_city_samples.py --base "$BASE"

# Keepalive plan (dry-run): city/MN only — never Pulse/tx-decision
.venv/bin/python scripts/city_keepalive.py --base "$BASE"

# Execute settles from local buyer env only
BUYER_ENV=/home/keef/secrets/x402-buyer.env \
  .venv/bin/python scripts/city_keepalive.py --execute
```

Demand truth: `GET $BASE/demand` → read `sales_external` / `conversion`, not challenge volume.  
Operator settles are not customers.
