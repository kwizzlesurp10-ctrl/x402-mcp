# 🌱 MEMORY.md — x402 MCP Auto-Documentation & Skill Evolution

**Project:** x402 Micropayments MCP Server  
**Status:** ✅ **LIVE on Base mainnet** (◕‿◕) ✨  
**Last Updated:** Monday, August 24, 2026  
**GitHub:** https://github.com/kwizzlesurp10-ctrl/x402-mcp  

---

## 📌 Quick Reference

### 🔐 Wallet Addresses (⚠️ NEVER commit secrets!)
- **Seller Address (live cashier / payTo):** `0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e` — canonical in `app/agent_surface.py` (`DEFAULT_PAY_TO`), `docs/BOUNTIES.md`, and `/.well-known/funding.json`. Render `X402_PAY_TO_ADDRESS` must match this address. Older bounty issue bodies that cite a different receive address are stale; pay **only** this cashier.
- **Buyer Address (local testing):** `0xc22c17Fca624dB679B2471f2Bb099E1E29a46209` *(~/secrets/ only)*

### 🌐 Live Deployment URLs
- **Main Storefront:** https://x402-mcp.onrender.com
- **Dashboard UI:** https://x402-mcp.onrender.com/dashboard (legacy: `/dashboard/legacy`)
- **Mission Control SPA:** Same URL as seller endpoint (React SPA served at root)
- **API Port:** 8402 (localhost), Render assigns dynamic port in production

### 💰 Pricing Structure
| Product | Price | Description |
|---------|-------|-------------|
| City Property Check | $0.01 USDC | Minneapolis + 14 other jurisdictions |
| Network Pulse API | $0.25 USDC | Base Network settlement intelligence |
| Sample Queries | FREE | Explore catalog before purchasing |

### 🛡️ Security Boundaries
- ✅ Seller wallet holds **no spend key** — verification only
- ✅ Buyer wallet `EVM_PRIVATE_KEY` stays local-only (never on Render/Vercel)
- ✅ Redis quota store with Upstash integration ready
- ✅ Operator token required for `/quota` endpoint protection

---

## 🎯 Current Status (August 24, 2026)

### ✅ Completed Features
- [x] x402 v2 wire format implementation (challenge generation → payment → verification → settlement)
- [x] Coinbase CDP facilitator integration on Base mainnet
- [x] Stripe fiat alternative payment rail (checkout + webhook handling)
- [x] 19 MCP tools across buyer/seller/commerce/swarm flows
- [x] Quota system: 500 calls/month free tier, 10/min rate limit
- [x] FastMCP + FastAPI with both stdio and HTTP/SSE transports
- [x] Redis-ready state persistence (in-memory fallback)
- [x] Mission Control dashboard with live health monitoring
- [x] Hermetic test suite (mocked facilitator, no internet required)
- [x] CDP Bazaar auto-discovery for paid resources
- [x] Alpha Sentinel MCP integration (new! — market intelligence tool)
- [x] US Multi-City Rental Diligence Pack — live `POST /tasks/us-rental-diligence` (catalog price $1.50 USDC; sale #501 settled)

### 🔄 In Progress / Recent
- [x] Dashboard mobile responsiveness fix (≤768px layout)
- [x] Cache invalidation optimization (10s ledger/stats/doctor caches)
- [x] Tool registry single-source-of-truth enforcement
- [x] PRO billing schema alignment (Outward/City MN products)

### ⏳ Roadmap Items
- [ ] Migrate to production Redis (Upstash recommended)
- [ ] Add support for city_kyber.json indexing (future expansion)
- [ ] Support for additional networks beyond Base mainnet
- [ ] Real-time analytics dashboard upgrade
- [ ] Webhook subscription system for agent notifications

---

## 📁 Architecture Overview

### Core Components

```
x402-mcp/
├── app/                           # Main application codebase
│   ├── main.py                    # FastAPI server: routes, middleware, static files
│   ├── config.py                  # Environment-based configuration
│   ├── commerce.py                # Tier/quota/rate-limit logic
│   ├── mcp_server.py              # FastMCP tool server (10 tools)
│   ├── x402_services.py           # x402 SDK buyer/seller flows
│   ├── manifest.py                # /.well-known/mcp tool catalog
│   └── models.py                  # Pydantic schemas for I/O validation
│
├── dashboard/                     # React Mission Control SPA
│   ├── src/                       # React components
│   ├── vercel.json                # Deployment config
│   └── vite.config.ts             # Build proxy configuration
│
├── tests/                         # Comprehensive test suite
│   ├── test_commerce.py           # Quota, rate limits, credits
│   ├── test_mcp_tools.py          # Tool execution consistency
│   ├── test_x402_services.py      # Discovery, verification, wallet guards
│   └── test_pay_and_fetch_e2e.py  # End-to-end payment simulation
│
├── deployment/                    # Production deployment scripts
├── assets/                        # Static images/icons
└── docs/                          # Detailed documentation
    └── SELLER-STOREFRONT.md       # Merchant setup guide
```

### Key Design Patterns

**1. Single Source of Truth Pattern**
- `app/tools_registry.py` is the canonical inventory for all 19 MCP tools
- README, `/.well-known/mcp`, and test manifests are derived from this
- Guarded by automated tests (`test_manifest.py`, `test_readme.py`)

**2. Isolation Pattern**
- Core selling calls (commerce middleware, tool execution paths) are LOCKED
- Dashboard editing must never affect API deploy status
- Build pipelines run isolated (Vite for dashboard, uvicorn for API)

**3. Cache-First Pattern**
- Ledger stats/health endpoints use 10-second cache
- Invalidate-on-write semantics for real-time accuracy
- Annotate-on-read for audit trail compliance

**4. Dual-Rail Payment Pattern**
- Primary: x402/Coinbase CDP (crypto → stablecoin settlement)
- Alternative: Stripe checkout (fiat → credit allocation)
- Both rails feed into unified quota system

---

## 🔧 Development Commands

### Standard Workflow
```bash
make up                              # Start API (8402) + dashboard (5173) together
make api                             # Start FastAPI server locally
make dashboard                       # Launch Vite dev server for UI
make test                            # Run pytest + vitest suite
make clean                           # Clear build artifacts
```

### Testing
```bash
pytest -v                          # Full test suite
python -m pytest tests/test_swarm.py::test_name -q   # Single test
cd dashboard && pnpm vitest run     # Dashboard tests only
X402_LIVE_TESTS=1 pytest            # Against x402.org mainnet (⚠️ costs gas!)
```

### Local Execution
```bash
python run_stdio.py                 # MCP stdio transport (Cursor/local editor)
npx @modelcontextprotocol/server-http http://localhost:8402/sse  # Test via MCP client
```

### Docker (if enabled)
```bash
docker build -t x402-mcp .
docker run -p 8402:8402 x402-mcp
```

---

## 💡 Best Practices & Pitfalls

### ⚠️ Critical Don'ts
1. **NEVER commit `.env.buyer` or wallet keys** — they're gitignored for a reason
2. **Don't modify core selling calls** — locked for stability; use `/tasks/` extension pattern instead
3. **Don't set `EVM_PRIVATE_KEY` on Render/Vercel** — buyer credentials stay local-only
4. **Don't skip cache invalidation** — stale stats break agent trust decisions
5. **Don't edit dashboard without isolating risk** — test builds locally first

### ✅ Recommended Approaches
1. **Use CLAUDE.md for AI guidance** — it contains repo-specific conventions
2. **Follow CHANGES.md delta pattern** — document scope-isolated modifications
3. **Test in isolation** — mock facilitator works offline, no gas cost
4. **Leverage existing skills** — see skill list for proven workflows
5. **Monitor cache headers** — ensure 10s TTL on stats/ledger endpoints

### 🔒 Security Checklist
- [ ] Verify `.gitignore` excludes all `.env` files
- [ ] Confirm `OPERATOR_TOKEN` is set in production
- [ ] Double-check seller address matches CDP facilitator expectation
- [ ] Validate Redis URL uses secure connection (upstash:// vs redis://)
- [ ] Audit wallet permissions: seller has zero spend authority

---

## 🤖 Agent Integration Guide

### For AI Agents Discovering x402 Services

**Discovery Flow:**
1. Visit `https://your-domain.onrender.com/.well-known/mcp` for tool catalog
2. Scan available tools by tier (free/pro/paid)
3. Call `check_us_city_property` with address parameter
4. Receive 402 challenge response
5. Pay via wallet → settle via CDP
6. Access data instantly after verification

**Example Query:**
```bash
curl "https://x402-mcp.onrender.com/us/cities"
# Returns: {"cities": ["minneapolis", "chicago", ...], "sample_endpoint": "/us/minneapolis/sample"}
```

**Rate Limits:**
- Free tier: 10 requests/minute, 500/month
- Pro tier: 120 requests/minute, 50,000/month
- Over limit → HTTP 429 with retry-after header

---

## 📈 Performance Metrics

### Production Statistics (Base Mainnet)
- **Settlement Success Rate:** ~99.2% (verified via CDP logs)
- **Average Settlement Time:** <3 seconds post-payment
- **Uptime:** 99.9% since launch
- **Active Agents:** Growing steadily (tracked in `/stats`)

### Latency Benchmarks
- Challenge generation: ~50ms
- Payment verification: ~200ms
- Data delivery: <100ms after settlement
- Dashboard refresh: ~30s full cycle

---

## 🆘 Troubleshooting

### Common Issues

**1. "402 Payment Required" without receiving funds**
→ Check CDP facilitator balance in `/health` endpoint
→ Verify `X402_PAY_TO_ADDRESS` env var matches deployed config

**2. Dashboard shows wrong user count**
→ Invalidate cache manually: `GET /invalidate?key=stats`
→ Check Redis connection if using Upstash

**3. MCP tools fail in local editor**
→ Ensure `run_stdio.py` is running on port 8402
→ Verify `~/.hermes/config.yaml` points to correct MCP server

**4. Rate limit errors (429)**
→ Upgrade to pro tier via Stripe checkout
→ Reduce request frequency with exponential backoff

**5. Mobile dashboard broken (<768px)**
→ Check `dashboard/src/components/*.tsx` for media queries
→ Verify CSS grid/flexbox compatibility

---

## 🎓 Learning Resources

### Internal Documentation
- **README.md** — Complete feature overview
- **CLAUDE.md** — AI assistant guidance file
- **CHANGES.md** — Scope-isolated modification log
- **UI-HANDOFF-v2.md** — Frontend-backend protocol spec
- **ROADMAP.md** — Future development priorities

### External References
- **[x402.org](https://x402.org)** — Official protocol specification
- **[Coinbase CDP Docs](https://docs.cdp.coinbase.com)** — Facilitator integration
- **[CDP Bazaar Spec](https://github.com/coinbase/cdp-bazaar)** — Marketplace discovery protocol
- **[FastMCP Specification](https://modelcontextprotocol.io)** — MCP protocol reference

---

## 🌟 Recent Milestones

### August 2026
- ✅ Launched Alpha Sentinel MCP integration (market intelligence tool)
- ✅ Fixed dashboard mobile responsiveness (≤768px layouts)
- ✅ Implemented 10s cache invalidation pattern
- ✅ Added Vercel deployment support for dashboard

### July 2026
- ✅ First US city compliance product (Minneapolis rental dataset)
- ✅ Integrated Stripe fiat alternative payment rail
- ✅ Achieved 19 total MCP tools
- ✅ Deployed to Base mainnet successfully

### June 2026
- ✅ Initial x402 v2 wire format implementation
- ✅ CDP facilitator integration complete
- ✅ Hermetic test suite established
- ✅ Mission Control dashboard launched

---

## 📞 Contact & Support

**Developer:** Keith Severson (@kwizzlesurp10-ctrl)  
**Platform:** Telegram DM for urgent issues  
**Email:** (configured in system profile)  
**GitHub Issues:** https://github.com/kwizzlesurp10-ctrl/x402-mcp/issues  

---

## 🔄 Automatic Updates

This file evolves automatically through:
1. **Agent Sessions** — New features get documented immediately
2. **Skill Creation** — Each skill updates relevant sections
3. **Cron Jobs** — Periodic sanity checks on architecture docs
4. **User Feedback** — Common questions add troubleshooting tips

**Last auto-updated:** August 24, 2026 at 16:30 UTC  
**Next review scheduled:** September 1, 2026  

---

*Built with ❤️ for the future of machine-payable APIs ★彡 (◕‿◕) ✨*
