# Roadmap

Status date: 2026-07-18. The server is live on Base mainnet at
https://x402-mcp.onrender.com with two payable products and USDC settlement
through the Coinbase CDP facilitator. This roadmap covers the next 90 days.

## Now → 30 days: catalog and first revenue

- [ ] Seed settlement: first settled mainnet sale, which catalogs the
      listings in the x402 Bazaar / CDP discovery (cataloging is
      settlement-triggered).
- [ ] Index products on [Agentic.Market](https://www.agentic.market) — CDP's
      discovery surface for the x402 ecosystem.
- [ ] Persist the product registry (listings currently in-memory; a restart
      drops them) and move quota/credit/ledger state to Redis
      (`REDIS_URL` is already wired — make it the deployed default).
- [ ] Keep the Pulse listing fresh via scheduled republish.

## 30 → 60 days: repeat the civic-data wedge

- [ ] Generalize the Minneapolis compliance pipeline into a city-portal
      adapter (ArcGIS + Socrata) with per-dataset schema mapping.
- [ ] Ship 3–5 more city compliance products (St. Paul, Chicago candidates)
      at $0.01–$0.05 per call, each x402-gated and Bazaar-discoverable.
- [ ] Publish the seller-storefront pattern (no spend key on the public
      host) as a standalone guide other CDP builders can copy.

## 60 → 90 days: close the buyer loop

- [ ] Open-source reference buyer agents on AgentKit + CDP Wallets that
      discover a Bazaar listing, pay via x402, and consume the data
      end to end.
- [ ] Multi-instance deploy behind the Redis quota store; uptime and
      settlement-latency metrics on the public dashboard.
- [ ] Evaluate Solana (SVM) mainnet listings — the seller already registers
      `solana:*` schemes; gate on facilitator support and demand signals.

## Principles

- Real data only: every product computes from live, inspectable sources
  (city open data, Base RPC, spot APIs). No mocked numbers.
- Sell-side stays keyless: the public host never holds a spending key.
- Registry-driven: tools and products flow from `app/tools_registry.py`
  and the swarm registry; README claims are test-guarded.
