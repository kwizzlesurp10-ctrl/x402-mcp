# BAZAAR_AUDIT.md

Audit of discoverable paid/free resources and MCP tools emitting bazaar.info for the x402-mcp storefront. Inspected live on 2026-09-11.

## 1. Free City Catalog

- **Resource URL**: `https://x402-mcp.onrender.com/us/cities`
- **Input shape**: `GET` (no parameters)
- **Example output**: JSON object with `network`, `price`, `network_caip2`, and a `cities` array containing 14 US cities. Each city object includes `code`, `name`, `state`, `service_name`, `price` ("$0.01"), `network`, `paid_url`, `sample_url`, `sample_address`, `sources_label`, `tags`, and `canonical_alias`.
- **Price**: Free (0 atomic units)
- **Under $0.10 agent filter**: Yes (Free)
- **payTo in 402 accepts**: N/A (Free endpoint, no 402 challenge issued)

## 2. Paid Property Check Endpoints (14 cities)

Each city has a paid endpoint at `https://x402-mcp.onrender.com/us/{code}/property-check`.
Live inspection performed on: `https://x402-mcp.onrender.com/us/mn/property-check`

- **Resource URL**: `https://x402-mcp.onrender.com/us/{code}/property-check` (where `{code}` is mn, sea, nyc, chi, den, sf, lax, bos, phi, orl, nola, moco, gain, kc)
- **Input shape**: `GET ?address=<street address 1-120 chars>`
- **Example output**: `missing` (requires valid x402 payment signature to retrieve body). The 402 Payment Required response header includes a `bazaar` extension with an `output.example` JSON showing fields like `city`, `city_name`, `state`, `address_queried`, `compliance_verdict`, `registrations`, `violation_cases`, `condemned_or_boarded`.
- **Price**: 10000 atomic units ($0.01 USDC)
- **Under $0.10 agent filter**: Yes
- **payTo in 402 accepts**: Yes (`0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e` is present in all three network accepts: Base eip155:8453, Solana, and Arbitrum eip155:42161).

## 3. Free Property Check Samples

Each city has a free fixed-address sample at `https://x402-mcp.onrender.com/us/{code}/property-check/sample`.
Live inspection performed on: `https://x402-mcp.onrender.com/us/mn/property-check/sample`

- **Resource URL**: `https://x402-mcp.onrender.com/us/{code}/property-check/sample`
- **Input shape**: `GET` (no parameters, returns data for a hardcoded sample address)
- **Example output**: JSON report with `sample: true`, `city`, `sample_address`, `note`, `paid_endpoint`, `price`, and a full `report` object containing `compliance_verdict`, `registrations`, `violation_cases`, `condemned_or_boarded`, `sources`, and `disclaimer`.
- **Price**: Free (0 atomic units)
- **Under $0.10 agent filter**: Yes (Free)
- **payTo in 402 accepts**: N/A (Free endpoint)

## 4. MCP Tools Emitting bazaar.info

The following MCP tools in `app/tools_registry.py` interact with the Bazaar discovery or property check endpoints:

- `discover_x402_bazaar`: Discovers paid HTTP APIs in the x402 Bazaar via the facilitator catalog.
- `catalog_bazaar_endpoint`: Passes `resource_url` plus `discovery_*` fields to catalog the endpoint in Bazaar.
- `list_us_cities`: Lists US City Open-Data Compliance Network cities with `paid_url`, `sample_url`, and price.
- `get_us_city_property_sample`: Gets a free fixed-address property compliance sample for one US city code.
- `check_us_city_property`: Runs a paid US city property compliance check via x402 on the same HTTP resource buyers use.

## 5. Gaps / Missing

- **Public Ledger**: The `/ledger` endpoint returns `{"detail":"Not Found"}`. There is no publicly readable ledger endpoint to verify settlement history without relying on GitHub issues or on-chain explorers.
- **Live Example Output for Paid Endpoints**: The actual JSON response body for paid endpoints is not publicly accessible without a valid x402 payment signature. The example output is only available embedded in the 402 challenge header's `bazaar` extension.
- **Bazaar Facilitator Catalog URL**: The public facilitator catalog URL is not directly exposed in the free HTTP endpoints; discovery relies on the MCP tools or the 402 challenge extensions.
