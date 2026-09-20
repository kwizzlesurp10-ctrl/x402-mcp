# BAZAAR_AUDIT.md — x402 Micropayments MCP

Audited 2026-09-17 against live service `https://x402-mcp.onrender.com`.

## Discoverable resources

### MCP tools (23 live tools, no price in tool schema — paid via x402 context)

| # | Tool | Description (truncated) |
|---|------|------------------------|
| 1 | x402.agent_card | Return the A2A Protocol v1.0 Agent ID Card and MCP server card |
| 2 | get_agent_card | Back-compat alias for x402.agent_card |
| 3 | x402.discover | Discover paid HTTP APIs via the facilitator catalog |
| 4 | x402.probe | Probe a URL for HTTP 402 PAYMENT-REQUIRED terms |
| 5 | x402.pay_and_fetch | Pay USDC via x402 and fetch a protected resource |
| 6 | x402.build_seller | Build seller-side x402 payment requirements |
| 7 | x402.verify | Verify an x402 PAYMENT-SIGNATURE |
| 8 | x402.networks | List supported settlement networks |
| 9 | commerce.pro_requirements | Build requirements for Pro quota tier |
| 10 | commerce.activate_pro | Verify Pro-tier x402 payment |
| 11 | commerce.credits_requirements | Build requirements for per-use MCP tool credits |
| 12 | commerce.purchase_credits | Verify payment and add tool credits |
| 13 | swarm.research | Compose a research product from free inputs |
| 14 | swarm.settle | Verify and settle buyer's x402 payment |
| 15 | swarm.revenue | Get swarm composite economics |
| 16 | pulse.base | Live Base Network Pulse: base fee, EIP-1559 projection |
| 17 | ops.metrics | Host OS telemetry: CPU, memory, swap, disk, network |
| 18 | city.list | List US City Open-Data Compliance Network cities |
| 19 | city.sample | Free fixed-address property compliance sample |
| 20 | city.check | Paid US city property compliance check via x402 |
| 21 | mailrail.send | Dispatch transactional receipts / alerts |
| 22 | mailrail.status | Inspect MailRail provider status |
| 23 | mailrail.inbound | Ingest incoming message or webhook |

### HTTP services (agentic-market.json)

| # | Service | URL | Method | Price | Under $0.10? | payTo |
|---|---------|-----|--------|-------|--------------|-------|
| 1 | us-rental-diligence | /tasks/us-rental-diligence | POST | 1.50 USDC | No | 0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e |
| 2 | base-tx-decision | /base/tx-decision | GET | 0.01 USDC | Yes | 0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e |
| 3 | base-finality-check | /base/finality-check | GET | 0.01 USDC | Yes | 0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e |
| 4 | us-city-compliance-network | /us/cities | GET | 0.01 USDC | Yes | 0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e |
| 5 | x402-mailrail-postmaster | /mailrail/inbound | POST | 0.00 USDC | Yes (free) | 0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e |

### US city property-check endpoints (catalog: /us/cities — 16 cities, all $0.01)

| Code | City | State | Service | Paid URL | Sample URL |
|------|------|-------|---------|----------|------------|
| mn | Minneapolis | MN | MN Rental License Check | /us/mn/property-check | /us/mn/property-check/sample |
| sea | Seattle | WA | Seattle Rental Registration | /us/sea/property-check | /us/sea/property-check/sample |
| nyc | New York City | NY | NYC HPD Violations Address | /us/nyc/property-check | /us/nyc/property-check/sample |
| chi | Chicago | IL | Chicago Building Violations | /us/chi/property-check | /us/chi/property-check/sample |
| den | Denver | CO | Denver STR License Check | /us/den/property-check | /us/den/property-check/sample |
| sf | San Francisco | CA | SF Housing NOV Check | /us/sf/property-check | /us/sf/property-check/sample |
| lax | Los Angeles | CA | LA Code Enforcement Open | /us/lax/property-check | /us/lax/property-check/sample |
| bos | Boston | MA | Boston Property Violations | /us/bos/property-check | /us/bos/property-check/sample |
| phi | Philadelphia | PA | Philly L&I Violations | /us/phi/property-check | /us/phi/property-check/sample |
| orl | Orlando | FL | Orlando STR License Check | /us/orl/property-check | /us/orl/property-check/sample |
| nola | New Orleans | LA | NOLA STR License Check | /us/nola/property-check | /us/nola/property-check/sample |
| moco | Montgomery County | MD | MoCo Housing License Check | /us/moco/property-check | /us/moco/property-check/sample |
| gain | Gainesville | FL | Gainesville Code Cases | /us/gain/property-check | /us/gain/property-check/sample |
| kc | Kansas City | MO | KC Exterior Building Violations | /us/kc/property-check | /us/kc/property-check/sample |
| atx | Austin | TX | Austin STR License Check | /us/atx/property-check | /us/atx/property-check/sample |
| sd | San Diego | CA | San Diego STR License Check | /us/sd/property-check | /us/sd/property-check/sample |

## Live probe results

### Minneapolis paid endpoint (verified 2026-09-17)

```
GET /us/mn/property-check?address=1700+Penn+Ave+N
→ HTTP 402 PAYMENT-REQUIRED
  price: $0.01
  network: eip155:8453
  accepts[0]: USDC 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913, amount 10000 atomic, payTo 0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e, maxTimeoutSeconds 300
  x402Version: 2
```

- price under $0.10 filter: **yes** ($0.01)
- payTo matches funding.json `0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e`: **yes**
- free sample exists: **yes** (`/us/mn/property-check/sample`)

### Free sample endpoint (verified live)

```
GET /us/mn/property-check/sample → HTTP 200, sample_address 1700 Penn Ave N, compliance_verdict licensed_with_violations
```

### Discovery gaps

| Resource | Status |
|----------|--------|
| /us/cities catalog | live, 16 cities |
| /us/mn/property-check | live, 402 at $0.01, payTo verified |
| /us/mn/property-check/sample | live, free |
| /us/sea/property-check | listed in catalog, not probed live |
| /us/nyc/property-check | listed in catalog, not probed live |
| /us/chi/property-check | listed in catalog, not probed live |
| /us/den/property-check | listed in catalog, not probed live |
| /us/sf/property-check | listed in catalog, not probed live |
| /us/lax/property-check | listed in catalog, not probed live |
| /us/bos/property-check | listed in catalog, not probed live |
| /us/phi/property-check | listed in catalog, not probed live |
| /us/orl/property-check | listed in catalog, not probed live |
| /us/nola/property-check | listed in catalog, not probed live |
| /us/moco/property-check | listed in catalog, not probed live |
| /us/gain/property-check | listed in catalog, not probed live |
| /us/kc/property-check | listed in catalog, not probed live |
| /us/atx/property-check | listed in catalog, not probed live |
| /us/sd/property-check | listed in catalog, not probed live |
| /base/tx-decision | listed, not probed live |
| /base/finality-check | listed, not probed live |
| /tasks/us-rental-diligence | listed, not probed live |
| /mailrail/inbound | listed, not probed live |
| /bazaar.info | **missing** (404) |
| MCP tools (23) | listed in server-card.json, not individually probed |

## Summary

- 5 discoverable services (4 paid, 1 free), all at $0.01 or less except us-rental-diligence at $1.50
- 16 city property-check endpoints, all listed at $0.01 — all under the common $0.10 agent filter
- 23 MCP tools surfaced via server-card.json
- Minneapolis paid probe confirms x402 v2 header, USDC, payTo `0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e`
- Gaps: 15 city endpoints + 4 HTTP services + bazaar.info not probed live (listed as `missing`, not padded)