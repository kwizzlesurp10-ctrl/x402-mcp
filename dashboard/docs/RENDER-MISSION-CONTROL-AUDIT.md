# Render Mission Control Audit Report

## 1. Deployment Drift Analysis
**Status:** 🔴 Drift Detected

### Pricing Discrepancies
- **Live Render (`https://x402-mcp.onrender.com`):** Legacy pricing observed ($0.01) in the UI Storefront.
- **Local Codebase (`ActiveStorefront.tsx`):** Currently lists `/mn/property-check` at $0.01.
- **Backend Truth (`tools_registry.py`):** Correctly lists `mn.property_diligence` at **$0.85**.
- **Impact:** High. Buyers see an incorrect price in the dashboard compared to what the backend enforces.

### Tool Registry Parity
- **Live Render:** Likely reflecting 20 MCP tools.
- **Local Codebase:** `TOOL_COUNT = 21`.
- **Impact:** Medium. One tool is missing from the live deployment's registry/UI.

### Discovery Metadata
- **Endpoints:** `.well-known/x402` and `.well-known/mcp` verified as present in architecture.

### Asset Hash Verification
- **Live Render Asset:** `index-D0wk-Czf.js` (Example)
- **Local Build:** Current build outputs vary. Need to sync `dashboard/dist/` to `app/static/mission_control/`.

## 2. Component Audit
### ActiveStorefront.tsx
- **Finding:** Hardcoded legacy pricing for `call-mn`.
- **Required Fix:** Update to "MARC-HD Compliance Verification" @ $0.85 USDC on Base.

### App.tsx (Strategic Assessment)
- **Finding:** Roadmap reflects "Invest in /mn/property-check" rather than "Shipped".
- **Required Fix:** Update `profit_routes` for `mn_invest`.

### Bubble.tsx (UX/UI)
- **Finding:** Bubble mouse trails are visually aggressive, potentially distracting from telemetry.
- **Required Fix:** Reduce trail length, scale, and opacity.

## 3. Build & Distribution
- **Current State:** Static assets are stored in `app/static/mission_control/`.
- **Drift:** Local `dashboard/dist/` has not been synchronized to the static serving directory.

## 4. Checklist for Resolution
- [ ] Update `ActiveStorefront.tsx` pricing/naming.
- [ ] Update `App.tsx` roadmap.
- [ ] Tame `Bubble.tsx` visual parameters.
- [ ] Execute `pnpm run build` and sync to `app/static/mission_control/`.
- [ ] Verify 21 MCP tools are visible in UI.
- [ ] Deploy updated bundle to Render.
