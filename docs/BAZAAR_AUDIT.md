# BAZAAR_AUDIT.md

Add-only audit of every discoverable paid/free resource in the x402-mcp Bazaar. No `app/` edits. Filled from the live catalog, free samples, and the `.well-known/x402` manifest.

## Catalog summary (live at `/us/cities`)

| # | City code | Service | Price | Paid URL | Under $0.10 filter? |
|---|-----------|---------|-------|----------|---------------------|
| 1 | mn | MN Rental License Check | $0.01 | /us/mn/property-check | ✅ yes |
| 2 | sea | Seattle Rental Registration | $0.01 | /us/sea/property-check | ✅ yes |
| 3 | nyc | NYC HPD Violations Address | $0.01 | /us/nyc/property-check | ✅ yes |
| 4 | chi | Chicago Building Violations | $0.01 | /us/chi/property-check | ✅ yes |
| 5 | den | Denver STR License Check | $0.01 | /us/den/property-check | ✅ yes |
| 6 | sf | SF Housing NOV Check | $0.01 | /us/sf/property-check | ✅ yes |
| 7 | lax | LA Code Enforcement Open | $0.01 | /us/lax/property-check | ✅ yes |
| 8 | bos | Boston Property Violations | $0.01 | /us/bos/property-check | ✅ yes |
| 9 | phi | Philly L&I Violations | $0.01 | /us/phi/property-check | ✅ yes |
| 10 | orl | Orlando STR License Check | $0.01 | /us/orl/property-check | ✅ yes |
| 11 | nola | NOLA STR License Check | $0.01 | /us/nola/property-check | ✅ yes |
| 12 | moco | MoCo Housing License Check | $0.01 | /us/moco/property-check | ✅ yes |
| 13 | gain | Gainesville Code Cases | $0.01 | /us/gain/property-check | ✅ yes |
| 14 | kc | KC Exterior Building Violations | $0.01 | /us/kc/property-check | ✅ yes |
| 15 | atx | Austin STR License Check | $0.01 | /us/atx/property-check | ✅ yes |
| 16 | sd | San Diego STR License Check | $0.01 | /us/sd/property-check | ✅ yes |

All 16 cities are paid resources at $0.01 USDC on Base (`eip155:8453`, asset `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`). All are under the common $0.10 agent filter. Pay-to address: `0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e`.

## Free resources (no payment required)

| URL | What it returns |
|-----|-----------------|
| `/us/cities` | Full city catalog (JSON) |
| `/us/{code}/property-check/sample` | Fixed-address sample report for each city |
| `/.well-known/x402` | Payment manifest |
| `/.well-known/agent-card.json` | Agent identity card |
| `/.well-known/agents.json` | Agents directory |
| `/.well-known/mcp` | MCP server card |
| `/openapi.json` | OpenAPI spec |
| `/llms.txt` | LLM context file |
| `/pulse` | Service health |

## Paid resource input shape & example output

**GET** `/us/{city_code}/property-check?address={street}`

- Input: `city_code` path (mn|sea|nyc|chi|den|sf|lax|bos|phi|orl|nola|moco|gain|kc|atx|sd), `address` query (1–120 chars)
- Example paid call: `https://x402-mcp.onrender.com/us/mn/property-check?address=1700+Penn+Ave+N`
- Example free sample: `https://x402-mcp.onrender.com/us/mn/property-check/sample`

**Sample output** (Minneapolis, 1700 Penn Ave N):
```json
{
  "sample": true,
  "city": "mn",
  "sample_address": "1700 Penn Ave N",
  "report": {
    "address_queried": "1700 Penn Ave N",
    "compliance_verdict": "licensed_with_violations",
    "registrations": [{
      "address": "1700 PENN AVE N",
      "apn": "1602924320087",
      "license_number": "LIC394217",
      "status": "Active",
      "tier": "Tier 1",
      "category": "CONV",
      "licensed_units": 1,
      "owner_name": "Bobbie Evans",
      "issue_date": "2021-05-24",
      "expiration_date": "2027-03-01",
      "ward": "5",
      "neighborhood": "Willard - Hay",
      "community": "Near North",
      "short_term_rental": "No"
    }]
  }
}
```

**POST** `/tasks/us-rental-diligence` — composite pack: `{properties:[{city_code,address}]}`, $1.50 USDC for up to 5 addresses.

**GET** `/base/tx-decision?gas=usdc&urgency=flexible` — $0.01, EIP-1559 fee recommendation.

**GET** `/base/finality-check?tx=0x...` — $0.01, tx status classification.

## Gaps listed as `missing`

- No `agenticMarket` resource listed in `.well-known/x402` resource_details (field exists in agent-card.json response body but is not a priced x402 resource).
- `/mailrail/inbound`, `/mailrail/inbox`, `/mailrail/stats` — not listed as priced x402 resources in the manifest; marked free in agent-card skills but no x402 price entry.
- `/us/{code}/property-check` canonical alias paths (e.g., `/mn/property-check`) are not separately priced in the manifest; they redirect to the `/us/` variant.
- No `examples` field populated for any resource detail in the manifest.
- No `description` field for most resource entries in `.well-known/x402`.

## Pay-to confirmation

All paid endpoints return `402 PAYMENT-REQUIRED` with the correct `payTo: 0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e` in the challenge body. The machine cashier at `/.well-known/funding.json` confirms the same payTo, network, and asset.

## Audit timestamp

Audited against live service at `https://x402-mcp.onrender.com` on 2026-09-19. No `app/` edits made.
