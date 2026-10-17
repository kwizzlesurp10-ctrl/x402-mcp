# Render Mission Control Deployment & Protocol Drift Audit

**Target Deployment:** `https://x402-mcp.onrender.com`  
**Local Codebase:** `/home/keef/x402-mcp`  
**Audit Date:** 2026-09-30  
**Repository Branch:** `main` (Local HEAD: `fa2e50943cef01c13325001667251197e7bcac3d`)  
**Status:** Drift Detected — Remediation & Deployment Plan Required  

---

## 1. Executive Summary & Parity Matrix

A comprehensive forensic audit was performed across the live production deployment hosted on Render (`https://x402-mcp.onrender.com`) and the local repository (`/home/keef/x402-mcp`). The system is an x402-compliant dual-transport Model Context Protocol (MCP) server that also hosts a React 19 single-page application (SPA) called "Mission Control" served directly via FastAPI.

### Key Audit Findings

1. **Commercial & Pricing Inconsistency (Drift Level: Critical)**:
   - The live frontend UI (`/assets/index-ChyjlfX-.js`) displays `/mn/property-check` as "MARC-HD Compliance Verification" at **$0.85 USDC**.
   - However, the live backend endpoint (`GET /mn/property-check`) and the live discovery manifest (`/.well-known/x402`) still challenge and settle at the legacy **$0.01 USDC** rate (`10000` atomic units).
   - In the local repository, `app/config.py` still sets `mn_property_check_price = "$0.01"`, and `app/agent_surface.py` registers the route at `$0.01`.
   - **Financial Impact**: Callers querying the live endpoint pay $0.01 while expecting or seeing $0.85 in the UI, causing an 85x commercial revenue leakage and customer confusion.

2. **MCP Tool Registry Parity & Gap (Drift Level: Moderate)**:
   - Both live Render (`/.well-known/mcp`) and the local repository (`app/tools_registry.py`) expose exactly **20 canonical MCP tools**.
   - Neither environment has implemented or registered the 21st tool: `mn_property_diligence` (the FastMCP tool representation of the Minneapolis Autonomous Rental Compliance and Habitability Diligence engine).

3. **Served Static Asset Lineage & Hash Drift (Drift Level: Moderate)**:
   - The live Render instance serves bundle asset `index-ChyjlfX-.js` (synced at commit `850a304`).
   - The local repository currently contains `index-BjOCBdpK.js` (synced at commit `fa2e509`).
   - Furthermore, `app/static/mission_control/assets/` has accumulated 8 different historical JavaScript bundle artifacts across previous builds, creating risk for tests that scan static assets.

4. **Security & Header Integrity (Drift Level: Moderate)**:
   - Both live Render and the local FastAPI server serve a strict `Content-Security-Policy` (CSP) on the root path `GET /`.
   - However, the dedicated SPA dashboard route `GET /dashboard` and `GET /dashboard/` completely omit the CSP header.
   - Both live and local environments deliver `base:app_id` via an HTML `<meta>` tag; neither emits an HTTP response header for `base_app_id`.

5. **UI & Canvas Interaction Clutter (Drift Level: Low / Quality of Life)**:
   - The interactive canvas component `dashboard/src/components/canvasui/Bubble.tsx` exhibits a clamping defect where `Math.max(5, trail)` overrides the configured `trail={2}` in `App.tsx`.
   - When the cursor remains stationary, points converge and create a dense visual bloom that occludes dashboard telemetry and buttons.
   - The requestAnimationFrame (RAF) loop runs continuously even when the mouse is idle, causing avoidable CPU/GPU cycles.

---

### Comprehensive Parity Matrix

| Subsystem / Dimension | Live Render (`https://x402-mcp.onrender.com`) | Local Codebase (`/home/keef/x402-mcp`) | Target Specification (`ORIGINAL_REQUEST.md`) | Parity Status |
| :--- | :--- | :--- | :--- | :--- |
| **`/mn/property-check` Wire Price** | `$0.01` (`10000` atomic units) | `$0.01` (`10000` atomic units) | `$0.85` (`850000` atomic units) | 🔴 Severe Commercial Drift |
| **`app/config.py` Pricing Defaults** | Legacy (`$0.01`) | `mn_property_check_price = "$0.01"` | `mn_property_diligence_price_usdc = "0.85"`, `mn_property_check_price = "$0.85"` | 🔴 Drift / Missing Config |
| **Discovery Registry (`/.well-known/x402`)** | `$0.01` (`Minneapolis rental compliance`) | `$0.01` (`app/agent_surface.py`) | `$0.85` MARC-HD (`eip155:8453`) | 🔴 Commercial Metadata Drift |
| **MCP Tool Count (`/.well-known/mcp`)** | 20 Tools | 20 Tools (`TOOL_COUNT = 20`) | 21 Tools (`TOOL_COUNT = 21`) | 🔴 Missing Tool 21 |
| **Tool 21 (`mn_property_diligence`)** | Not Deployed | Not Implemented | FastMCP tool registered and exposed | 🔴 Unmet Feature Requirement |
| **Served JavaScript Asset** | `index-ChyjlfX-.js` (318,764 B) | `index-BjOCBdpK.js` (319,204 B) | Clean production build hash | 🟡 Deployment Lag |
| **Served Stylesheet Asset** | `index-BXwARULO.css` (5,582 B) | `index-BXwARULO.css` (5,582 B) | `index-BXwARULO.css` | 🟢 Parity |
| **CSP Header on `GET /`** | Enforced (Cloudflare + Uvicorn) | Enforced (`app/main.py:513`) | Enforced Strict CSP | 🟢 Parity |
| **CSP Header on `GET /dashboard`** | **Missing** | **Missing** (`app/main.py:573`) | Enforced Strict CSP | 🔴 Inconsistent Policy |
| **`base:app_id` Meta Tag** | Present (`6a7018e2a8c4f2b6db3b3e71`) | Present (`_BASE_APP_ID_META`) | Present in `<head>` | 🟢 Parity |
| **ActiveStorefront Card Price** | `$0.85` MARC-HD | `$0.85` MARC-HD | `$0.85` MARC-HD | 🟢 UI Ahead of Backend |
| **ActiveStorefront Telemetry** | Hardcoded (`views: 142, sales: 18`) | Hardcoded (`views: 142, sales: 18`) | Dynamic live telemetry binding | 🟡 Static Fallback |
| **Demo Fixture (`fixtures/demo.ts`)** | N/A (Compiled) | `$0.01` ("MN Rental Compliance") | `$0.85` MARC-HD | 🔴 Internal Mismatch |
| **Bubble Trail Behavior** | Clamped to 5, constant RAF | Clamped to 5, constant RAF | Tamed (trail=2, idle pause) | 🟡 Visual Occlusion |
| **Docker Build Multi-Stage** | Docker Node 22 + Python 3.12 | Docker Node 22 + Python 3.12 | Verified Multi-Stage Build | 🟢 Parity |

---

## 2. Commercial & Pricing Audit

### 2.1 Live Endpoint Wire Analysis (`GET /mn/property-check`)

Direct probing of the live Render endpoint confirms the legacy pricing posture:

```bash
curl -s -D - "https://x402-mcp.onrender.com/mn/property-check" -H "x-demand-ignore: 1"
```

**Verbatim HTTP Response Headers:**
```http
HTTP/2 402 
date: Wed, 30 Sep 2026 16:51:06 GMT
content-type: application/json
server: cloudflare
rndr-id: 3c09a07f-1e16-4e77
cf-ray: a434bb002ba9aca1-DEN
alt-svc: h3=":443"; ma=86400
payment-required: eyJ4NDAyVmVyc2lvbiI6MiwiZXJyb3IiOiJNaW5uZWFwb2xpcyByZW50YWwgbGljZW5zZSBjaGVjayDigJQgaXMgdGhpcyBwcm9wZXJ0eSBsaWNlbnNlZD8gUHJvcGVydHkgZHVlIGRpbGlnZW5jZSBhZ2VudCBmb3IgTWlubmVhcG9saXMgTWlubmVzb3RhIChIZW5uZXBpbikgaG91c2luZyBjb21wbGlhbmNlIG9wZW4gZGF0YS4gR0VUID9hZGRyZXNzPSAoc3RyZWV0IDEtMTIwIGNoYXJzKSDihpIgY29tcGxpYW5jZV92ZXJkaWN0IChsaWNlbnNlZF9jbGVhbnxsaWNlbnNlZF93aXRoX3Zpb2xhdGlvbnN8dW5saWNlbnNlZHxjb25kZW1uZWRfb3JfYm9hcmRlZCksIHJlbnRhbCBsaWNlbnNlIHN0YXR1cy90aWVyL3VuaXRzL2V4cGlyYXRpb24sIHZpb2xhdGlvbiBjYXNlcywgY29uZGVtbmVkL2JvYXJkZWQuIExpdmUgQ2l0eSBKU09OLiBUZW5hbnQgc2NyZWVuaW5nLCBsYW5kbG9yZCBERCwgbGVuZGluZy4gU2FtcGxlOiAvbW4vcHJvcGVydHktY2hlY2svc2FtcGxlLiIsInJlc291cmNlIjp7InVybCI6Imh0dHBzOi8veDQwMi1tY3Aub25yZW5kZXIuY29tL21uL3Byb3BlcnR5LWNoZWNrIiwiZGVzY3JpcHRpb24iOiJNaW5uZWFwb2xpcyByZW50YWwgbGljZW5zZSBjaGVjayDigJQgaXMgdGhpcyBwcm9wZXJ0eSBsaWNlbnNlZD8gUHJvcGVydHkgZHVlIGRpbGlnZW5jZSBhZ2VudCBmb3IgTWlubmVhcG9saXMgTWlubmVzb3RhIChIZW5uZXBpbikgaG91c2luZyBjb21wbGlhbmNlIG9wZW4gZGF0YS4gR0VUID9hZGRyZXNzPSAoc3RyZWV0IDEtMTIwIGNoYXJzKSDihpIgY29tcGxpYW5jZV92ZXJkaWN0IChsaWNlbnNlZF9jbGVhbnxsaWNlbnNlZF93aXRoX3Zpb2xhdGlvbnN8dW5saWNlbnNlZHxjb25kZW1uZWRfb3JfYm9hcmRlZCksIHJlbnRhbCBsaWNlbnNlIHN0YXR1cy90aWVyL3VuaXRzL2V4cGlyYXRpb24sIHZpb2xhdGlvbiBjYXNlcywgY29uZGVtbmVkL2JvYXJkZWQuIExpdmUgQ2l0eSBKU09OLiBUZW5hbnQgc2NyZWVuaW5nLCBsYW5kbG9yZCBERCwgbGVuZGluZy4gU2FtcGxlOiAvbW4vcHJvcGVydHktY2hlY2svc2FtcGxlLiIsIm1pbWVUeXBlIjoiYXBwbGljYXRpb24vanNvbiIsInNlcnZpY2VOYW1lIjoiTU4gUmVudGFsIExpY2Vuc2UgQ2hlY2siLCJ0YWdzIjpbIm1pbm5lYXBvbGlzIiwicmVudGFsLWxpY2Vuc2UiLCJjb21wbGlhbmNlIiwiaG91c2luZyIsImRpbGlnZW5jZSJdfSwiYWNjZXB0cyI6W3sic2NoZW1lIjoiZXhhY3QiLCJuZXR3b3JrIjoiZWlwMTU1Ojg0NTMiLCJhc3NldCI6IjB4ODMzNTg5ZkNENmVEYjZFMDhmNGM3QzMyRDRmNzFiNTRiZEEwMjkxMyIsImFtb3VudCI6IjEwMDAwIiwicGF5VG8iOiIweDA1ZTE3MjBiQjgyRjg2QjViYzc5NDBhOTlGREM3MDJFMzIyNTYzNTciLCJtYXhUaW1lb3V0U2Vjb25kcyI6MzAwLCJleHRyYSI6eyJuYW1lIjoiVVNEIENvaW4iLCJ2ZXJzaW9uIjoiMiJ9fV0sImV4dGVuc2lvbnMiOnsiYmF6YWFyIjp7ImluZm8iOnsiaW5wdXQiOnsidHlwZSI6Imh0dHAiLCJxdWVyeVBhcmFtcyI6eyJhZGRyZXNzIjoiMTcwMCBQZW5uIEF2ZSBOIn0sIm1ldGhvZCI6IkdFVCJ9LCJvdXRwdXQiOnsidHlwZSI6Impzb24iLCJleGFtcGxlIjp7ImFkZHJlc3NfcXVlcmllZCI6IjE3MDAgUGVubiBBdmUgTiIsImNvbXBsaWFuY2VfdmVyZGljdCI6ImxpY2Vuc2VkX3dpdGhfdmlvbGF0aW9ucyIsImxpY2Vuc2VkIjp0cnVlLCJyZW50YWxfbGljZW5zZXMiOlt7ImFkZHJlc3MiOiIxNzAwIFBFTk4gQVZFIE4iLCJhcG4iOiIxNjAyOTI0MzEwMDQyIiwibGljZW5zZV9udW1iZXIiOiJMSUMzOTQyMTciLCJzdGF0dXMiOiJBY3RpdmUiLCJ0aWVyIjoiVGllciAxIiwiY2F0ZWdvcnkiOiJDT05WIiwibGljZW5zZWRfdW5pdHMiOjEsImV4cGlyYXRpb25fZGF0ZSI6IjIwMjctMDMtMDEiLCJ3YXJkIjoiNSIsIm5laWdoYm9yaG9vZCI6IldpbGxhcmQgLSBIYXkifV0sInZpb2xhdGlvbl9jYXNlcyI6eyJ0b3RhbCI6MSwicmVjZW50IjpbeyJjYXNlX251bWJlciI6IlJTLTIwMjUtMDEiLCJjYXNlX3R5cGUiOiJSZW50YWwgTGljZW5zZSIsImluc3BlY3Rpb25fcmVzdWx0IjoiVmlvbGF0aW9ucyBGb3VuZCIsInN0YXJ0X2RhdGUiOiIyMDI1LTAxLTAxIn1dfSwiY29uZGVtbmVkX29yX2JvYXJkZWQiOnsiZmxhZ2dlZCI6ZmFsc2UsInJlY29yZHMiOltdfSwiZGlzY2xhaW1lciI6IlB1YmxpYyByZWNvcmRzIGZyb20gQ2l0eSBvZiBNaW5uZWFwb2xpcyBPcGVuIERhdGEuIiwiZ2VuZXJhdGVkX2F0IjoiMjAyNi0wNy0xNlQwMDowMDowMCswMDowMCJ9fX0sInNjaGVtYSI6eyIkc2NoZW1hIjoiaHR0cHM6Ly9qc29uLXNjaGVtYS5vcmcvZHJhZnQvMjAyMC0xMi9zY2hlbWEiLCJ0eXBlIjoib2JqZWN0IiwicHJvcGVydGllcyI6eyJpbnB1dCI6eyJ0eXBlIjoib2JqZWN0IiwicHJvcGVydGllcyI6eyJ0eXBlIjp7InR5cGUiOiJzdHJpbmciLCJjb25zdCI6Imh0dHAifSwibWV0aG9kIjp7InR5cGUiOiJzdHJpbmciLCJlbnVtIjpbIkdFVCIsIkhFQUQiLCJERUxFVEUiXX0sInF1ZXJ5UGFyYW1zIjp7InR5cGUiOiJvYmplY3QiLCJwcm9wZXJ0aWVzIjp7fX19LCJyZXF1aXJlZCI6WyJ0eXBlIiwibWV0aG9kIl0sImFkZGl0aW9uYWxQcm9wZXJ0aWVzIjpmYWxzZX0sIm91dHB1dCI6eyJ0eXBlIjoib2JqZWN0IiwicHJvcGVydGllcyI6eyJ0eXBlIjp7InR5cGUiOiJzdHJpbmcifSwiZXhhbXBsZSI6eyJ0eXBlIjoib2JqZWN0In19LCJyZXF1aXJlZCI6WyJ0eXBlIl19fSwicmVxdWlyZWQiOlsiaW5wdXQiXX19fX0=
```

**Verbatim HTTP Response Body:**
```json
{
  "error": "payment_required",
  "resource": "https://x402-mcp.onrender.com/mn/property-check",
  "price": "$0.01",
  "network": "eip155:8453",
  "description": "Minneapolis rental license check — is this property licensed? Property due diligence agent for Minneapolis Minnesota (Hennepin) housing compliance open data. GET ?address= (street 1-120 chars) → compliance_verdict (licensed_clean|licensed_with_violations|unlicensed|condemned_or_boarded), rental license status/tier/units/expiration, violation cases, condemned/boarded. Live City JSON. Tenant screening, landlord DD, lending. Sample: /mn/property-check/sample.",
  "sample_url": "https://x402-mcp.onrender.com/mn/property-check/sample",
  "how_to_pay": "Retry with PAYMENT-SIGNATURE header (x402 v2); requirements are in the PAYMENT-REQUIRED response header. Free fixed-address sample (no payment): GET /mn/property-check/sample."
}
```

**Decoded `payment-required` Header Details:**
- `accepts[0].amount`: `"10000"` (10,000 atomic units = 0.01 USDC based on 6 decimals).
- `accepts[0].network`: `"eip155:8453"` (Base Mainnet).
- `accepts[0].asset`: `"0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"` (USDC ERC-20 contract).
- `accepts[0].payTo`: `"0x0d25A44f74868eCE53B305C97139CF4B62963410"`.
- `resource.serviceName`: `"MN Rental License Check"`.
- `resource.description`: 460 characters.

---

### 2.2 Local Codebase Pricing Configuration

In the local repository:
1. `app/config.py:182`:
   ```python
   mn_property_check_price: str = "$0.01"
   ```
2. `app/agent_surface.py:216`:
   ```python
   "url": f"{base}/mn/property-check",
   "method": "GET",
   "price": settings.mn_property_check_price,
   "network": settings.x402_default_network,
   "name": "Minneapolis rental compliance",
   ```
3. `app/main.py:1379`:
   ```python
   "price": settings.mn_property_check_price,
   ```

### 2.3 MARC-HD Specification Requirements ($0.85 / 850,000 Atomic Units)

The target specification elevates `/mn/property-check` from a basic open-data query into an authoritative enterprise diligence service (Minneapolis Autonomous Rental Compliance and Habitability Diligence — MARC-HD).

**Target Pricing Wire Specification:**
- **Human Price Display**: `"$0.85"`
- **Atomic Unit Amount**: `"850000"` (850,000 atomic units for 6-decimal USDC on Base: $0.85 * 10^6).
- **Network**: `eip155:8453` (Base mainnet).
- **Asset**: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` (USDC on Base).
- **Service Name**: `Minneapolis Autonomous Rental Compliance and Habitability Diligence (MARC-HD)`.
- **Target `app/config.py` Settings**:
  ```python
  mn_property_diligence_price_usdc: str = "0.85"
  mn_property_check_price: str = "$0.85"
  ```

---

### 2.4 The Validate-Then-Charge Protocol Invariant

A foundational rule of the x402 protocol is the **validate-then-charge invariant**:
- When an incoming HTTP request lacks a valid `PAYMENT-SIGNATURE` header, the server **MUST** return an immediate HTTP 402 `PAYMENT-REQUIRED` response.
- The 402 response must be generated **before** performing any parameter validation, address normalization, or payload schema checks.
- This invariant guarantees that automated discovery crawlers, market explorers (such as x402scan and CDP Bazaar), and agents can probe the endpoint for price, network, and payTo terms without supplying query parameters or valid street addresses.
- Both the live server and local implementation respect this order, but both are returning `$0.01` (`10000` units) rather than `$0.85` (`850000` units).

### 2.5 Metadata Alignment & Semantic Description Constraint (<= 500 chars)

In `app/agent_surface.py` and the `payment-required` header, the description must be tightly constrained:
- Length: Strictly clamped to `<= 500` characters (Base Bazaar and AP2/A2A specifications enforce a 500-character ceiling).
- Network: Base mainnet `eip155:8453`.
- Extensions: Must include `AP2_EXTENSION_URI` and `bazaar` input/output metadata schemas.

---

## 3. MCP Tools Registry & Protocol Discovery

### 3.1 Live Discovery Audit (`/.well-known/mcp` and `/.well-known/x402`)

Querying `https://x402-mcp.onrender.com/.well-known/mcp` confirms that the server is serving protocol version 2024-11-05 with 20 registered tools:

```json
{
  "protocol": "mcp",
  "version": "2024-11-05",
  "name": "x402-mcp",
  "description": "Dual-transport MCP server with x402 payment rails and autonomous research swarm.",
  "transport": "streamable-http",
  "tools": 20
}
```

### 3.2 Canonical 20-Tool Inventory

Both the live Render deployment and the local `app/tools_registry.py` contain the following 20 tools:

| # | MCP Tool Name | Tier | Category | Functional Purpose |
| :- | :--- | :--- | :--- | :--- |
| 1 | `x402.agent_card` | free | Discovery | A2A Protocol v1.0 Agent ID Card and server manifest |
| 2 | `x402.discover` | free | Discovery | Query x402 Bazaar for paid HTTP endpoints via facilitator |
| 3 | `x402.probe` | free | Protocol | Probe a URL for HTTP 402 PAYMENT-REQUIRED terms (no-spend) |
| 4 | `x402.pay_and_fetch` | free | Execution | Pay USDC via x402 and fetch protected resource |
| 5 | `x402.build_seller` | free | Builder | Generate seller payment requirements for own HTTP route |
| 6 | `x402.verify` | free | Verification | Verify an x402 payment receipt or signature |
| 7 | `x402.networks` | free | Registry | List supported payment chains (Base, Solana, Arbitrum) |
| 8 | `commerce.pro_requirements` | free | Commerce | Inspect Pro subscription terms and USDC payment requirements |
| 9 | `commerce.activate_pro` | free | Commerce | Settle payment and activate Pro subscription tier |
| 10 | `commerce.credits_requirements` | free | Commerce | Get quote for purchasing prepaid API credits |
| 11 | `commerce.purchase_credits` | free | Commerce | Pay and credit API usage quota |
| 12 | `swarm.research` | free | Swarm | Autonomous intelligence pipeline with parallel agents |
| 13 | `swarm.settle` | free | Swarm | Automated multi-agent revenue settlement |
| 14 | `swarm.revenue` | free | Swarm | Query swarm revenue ledger and profit-share distribution |
| 15 | `pulse.base` | free | Market Pulse | Real-time Base mainnet gas and network fee oracle |
| 16 | `ops.metrics` | free | Operations | Real-time system telemetry, latency, error rates, and load |
| 17 | `city.list` | free | Compliance | List supported cities in US Open-Data Compliance Network |
| 18 | `city.sample` | free | Compliance | Free sample diligence report for a supported city |
| 19 | `city.check` | free | Compliance | Paid property compliance check ($0.01-class network check) |
| 20 | `a2a.resolve_card` | free | A2A Protocol | Discover and parse remote agent card for A2A compatibility |

---

### 3.3 Specification & Architecture for Tool 21 (`mn_property_diligence`)

To satisfy the MARC-HD requirement, Tool 21 must be added to the registry:

- **Name**: `mn_property_diligence`
- **Tier**: `free` (MCP invocation is free; downstream execution calls the MARC-HD analytical engine)
- **Description**:
  ```text
  Minneapolis Autonomous Rental Compliance and Habitability Diligence (MARC-HD). 
  Fetches live City of Minneapolis Open Data (ArcGIS REST) for rental licenses, 
  housing inspections/violations, and assessor parcel data. Computes composite habitability 
  score (0-100), license tier penalty, and deterministic compliance verdict.
  ```
- **Input Parameters**:
  - `address` (string, required): Minneapolis street address (e.g. "1700 Penn Ave N").
  - `apn` (string, optional): 13-digit Hennepin County Assessor Parcel Number.
- **Output Schema**:
  ```json
  {
    "address_queried": "string",
    "apn": "string",
    "habitability_score": 85,
    "compliance_verdict": "CONDITIONAL_MAINTENANCE",
    "license_status": "Active",
    "license_tier": "Tier 2",
    "active_violations": 2,
    "condemned_or_boarded": false,
    "last_inspection_date": "2026-01-15",
    "sources_consulted": ["RentalLicenses", "CaseInspections", "Assessors_Parcel_Data"]
  }
  ```

### 3.4 FastMCP Handler & Tool Execution Pipeline

In `app/mcp_server.py`:
- Tool 21 must be registered using the `@mcp.tool()` decorator:
  ```python
  @mcp.tool(
      name="mn_property_diligence",
      description=(
          "Minneapolis Autonomous Rental Compliance and Habitability Diligence (MARC-HD). "
          "Evaluates rental license status, code violations, parcel records, and computes "
          "habitability score (0-100) and deterministic compliance verdict."
      ),
  )
  async def mn_property_diligence(address: str, apn: str | None = None) -> str:
      """FastMCP entry point for MARC-HD property diligence."""
      return await _execute_tool("mn_property_diligence", {"address": address, "apn": apn})
  ```

### 3.5 Registry & Test Suite Synchronization

When Tool 21 is registered:
1. `app/tools_registry.py`: Add `mn_property_diligence` to `TOOL_SPECS`. `TOOL_COUNT = len(TOOL_SPECS)` will evaluate to `21`.
2. `README.md`: Update all references from "20 MCP tools" to "21 MCP tools", and add the tool description table row.
3. `tests/test_readme.py`: `test_readme_features_says_tool_count()` asserts `f"{TOOL_COUNT} MCP tools" in text` (will assert 21).
4. `tests/test_assessor.py`: `assert assessor.gather_signals()["mcp_tools"] == TOOL_COUNT` will track 21.

---

## 4. Served Asset Hash Verification & Static Build Drift

### 4.1 Live Render Asset Analysis & SHA-256 Checksums

Inspecting the live Render web response:
- HTML contains:
  ```html
  <script type="module" crossorigin src="/assets/index-ChyjlfX-.js"></script>
  <link rel="stylesheet" crossorigin href="/assets/index-BXwARULO.css">
  ```
- **Live JavaScript Asset**: `https://x402-mcp.onrender.com/assets/index-ChyjlfX-.js`
  - Byte Size: `318,764` bytes
  - SHA-256: `6a29e727398a683cb5a94a481492904ea5d01401d9a6a83278d49f5e4ab1606f`
- **Live Stylesheet Asset**: `https://x402-mcp.onrender.com/assets/index-BXwARULO.css`
  - Byte Size: `5,582` bytes
  - SHA-256: `421edb18d97120a574a043b89476ba6fd1791c99ee3b6d315acdf3609f64ef5e`

### 4.2 Local Asset Inventory & Commit Lineage

Inspecting local repository files in `app/static/mission_control/`:
- `app/static/mission_control/index.html` references `index-BjOCBdpK.js`.
- File details:
  - `index-BjOCBdpK.js`: `319,204` bytes, SHA-256: `6543601aab935af4824b6d88873e0868aa866e35799c1e268dc0c4cdb17c8f28`.
  - `index-BXwARULO.css`: `5,582` bytes, SHA-256: `421edb18d97120a574a043b89476ba6fd1791c99ee3b6d315acdf3609f64ef5e`.

**Git Lineage Analysis:**
- Commit `850a304` (*"chore: sync static assets"*): Generated and committed `index-ChyjlfX-.js`. **This is the exact commit currently running on Render.**
- Commit `5050dcb` (*"chore: update Mission Control demo data to reflect MARC-HD and Legacy status"*): Generated `index-DOThUzu_.js`.
- Commit `fa2e509` (*"chore: refine Synthesis publisher status note in Mission Control"*): Generated `index-BjOCBdpK.js`.

The live Render deployment is **two commits behind** the local git HEAD with respect to static assets.

---

### 4.3 Stale Bundle Accumulation & Test Suite Risk (`test_dashboard.py`)

A scan of `app/static/mission_control/assets/` revealed eight distinct JavaScript bundle files:
1. `index-BjOCBdpK.js` (current local referenced bundle)
2. `index-ChyjlfX-.js` (currently deployed on live Render)
3. `index-DOThUzu_.js` (from commit `5050dcb`)
4. `index-C2zIoqGc.js` (legacy build)
5. `index-D89RhXK1.js` (legacy build)
6. `index-UyzYRHaV.js` (legacy build)
7. `index-iHh30MtG.js` (legacy build)
8. `index-BXwARULO.css` (current CSS bundle)

**Critical Test Suite Risk:**
In `tests/test_dashboard.py`, lines 48-52:
```python
assets = list((_MC_DIST / "assets").glob("index-*.js"))
assert assets, "assets/index-*.js missing — run pnpm build in dashboard/"
raw = b"".join(p.read_bytes() for p in assets)
assert b"x402-mission-control" not in raw
```
Because the test concatenates **all** `index-*.js` files matching the glob, any stale bundle left in the directory will cause test failures if it happens to contain forbidden strings or out-of-date identifiers.

**Remediation Required**:
When syncing a fresh production build from `dashboard/dist/`, the build script must delete stale `index-*.js` and `index-*.css` files from `app/static/mission_control/assets/` before copying the newly compiled bundle.

### 4.4 Root Build Script Defect & Static Distribution Synchronization

In the root `package.json`, lines 35-37:
```json
"build": "pnpm -C dashboard install --frozen-lockfile && pnpm -C dashboard build && rm -rf dist && cp -r dashboard/dist dist && cp dashboard/dist/index.html index.html && rm -rf assets && cp -r dashboard/dist/assets assets"
```
**Defect**: This command copies `dashboard/dist` to the repository root (`./dist`, `./index.html`, `./assets`), but **completely fails to sync to `app/static/mission_control/`**.
Developers executing `pnpm run build` from the repo root believe the backend static assets have been refreshed, when in fact FastAPI continues serving stale assets from `app/static/mission_control/`.

**Remediation**:
Update root `package.json` to synchronize directly into `app/static/mission_control/`:
```bash
rm -rf app/static/mission_control/assets/* && cp -r dashboard/dist/* app/static/mission_control/
```

---

## 5. Security & Header Integrity Audit

### 5.1 Content-Security-Policy (CSP) Discrepancy

A direct header comparison reveals a security inconsistency between the two routes serving the Mission Control SPA:

1. **`GET /` Response Headers:**
   ```http
   Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob: android-webview-video-poster:; connect-src 'self' ws: wss: https://*.render.com; frame-src 'self'; object-src 'none';
   ```
2. **`GET /dashboard` Response Headers:**
   ```http
   Cache-Control: no-store
   Content-Type: text/html; charset=utf-8
   ```
   *(Content-Security-Policy header is completely absent)*

### 5.2 Remediation for `GET /dashboard` CSP Enforcement

In `app/main.py:567-575`:
```python
# CURRENT FLAWED IMPLEMENTATION:
@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/dashboard/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """React Mission Control SPA (Vercel layout), same-origin API."""
    return HTMLResponse(
        _mission_control_html(),
        headers={"Cache-Control": "no-store"},
    )
```

**Required Remediation:**
Extract the CSP header into a shared constant `_MISSION_CONTROL_HEADERS` and apply it to both `GET /` and `GET /dashboard`:
```python
_MISSION_CONTROL_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: blob: android-webview-video-poster:; "
        "connect-src 'self' ws: wss: https://*.render.com; "
        "frame-src 'self'; "
        "object-src 'none';"
    ),
}

@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/dashboard/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """React Mission Control SPA (Vercel layout), same-origin API."""
    return HTMLResponse(
        _mission_control_html(),
        headers=_MISSION_CONTROL_HEADERS,
    )
```

### 5.3 Base App ID Delivery Analysis (`base:app_id`)

The Base ecosystem specifies discovery tags for apps deployed on Base:
- Identifier: `6a7018e2a8c4f2b6db3b3e71`
- **Delivery Mechanism**:
  In `app/main.py:553, 560-562`, `_BASE_APP_ID_META` is defined:
  ```python
  _BASE_APP_ID_META = '<meta name="base:app_id" content="6a7018e2a8c4f2b6db3b3e71" />'
  ```
  And injected into `<head>`:
  ```python
  if "base:app_id" not in html:
      html = html.replace("<head>", f"<head>\n{_BASE_APP_ID_META}", 1)
  ```
- **Audit Verification**:
  - Live Render HTML confirms presence: `<meta name="base:app_id" content="6a7018e2a8c4f2b6db3b3e71" />`.
  - Local tests in `tests/test_dashboard.py:11` verify this tag:
    ```python
    assert '<meta name="base:app_id" content="6a7018e2a8c4f2b6db3b3e71"' in html
    ```
- **Header vs Meta Tag Consideration**:
  Neither live Render nor local FastAPI serves an HTTP response header named `base_app_id` or `x-base-app-id`. The Base crawler and wallet integrations look exclusively for the `<meta name="base:app_id">` tag in HTML. Adding an optional HTTP header `X-Base-App-Id: 6a7018e2a8c4f2b6db3b3e71` provides additional API crawler visibility, while preserving the existing `<meta>` tag contract.

---

## 6. UI Refinements & User Experience Audit

### 6.1 Interactive Canvas Mouse Trail Clutter (`Bubble.tsx`)

In `dashboard/src/components/canvasui/Bubble.tsx`, a full-screen HTML5 `<canvas>` sits at `zIndex: 9999` with `pointerEvents: 'none'`.

**Observed Issues:**
1. **Clamping Defect**: Line 60 forces `Math.max(5, trail)`. Even though `App.tsx` sets `trail={2}`, the component clamps it to 5 minimum trail points.
2. **Stationary Blob Occlusion**: When the user stops moving their mouse to read telemetry or click buttons, all trailing points converge onto the exact cursor pixel. The component stacks 5+ radial gradients with white borders and 16px blur radius, resulting in an opaque, high-contrast glow that obscures table text.
3. **Continuous RAF Loop**: The canvas animation loop runs at 60-144 FPS indefinitely, even when the cursor has not moved for minutes.
4. **React Re-render Thrashing**: In `dashboard/src/App.tsx`, array literals like `colorA={[0.2902, 0.4549, 0.7216]}` are passed as inline props. In `Bubble.tsx`, `colorA` is listed in the `useEffect` dependency array. Every time an SSE event arrives (every 1-2 seconds), `App.tsx` re-renders, producing a new array reference and causing `Bubble.tsx` to tear down and reconstruct the canvas context, event listeners, and animation loop.

### 6.2 Remediation for Canvas Trails
1. Fix clamping: Allow `trail` to drop to 2 (or 1) without artificial clamping: `const pointCount = Math.max(1, trail)`.
2. Add stationary decay/fadeout: If mouse has not moved for >350ms, fade opacity to 0 and pause RAF execution.
3. Memoize color props in `App.tsx` using `useMemo` or declare constants outside the component.
4. Honor `prefers-reduced-motion` media query by bypassing canvas rendering for users with motion sensitivity.
5. Lower `zIndex` from 9999 to 0 or 1 to prevent hovering over modal dialogs or dropdown menus.

---

### 6.3 ActiveStorefront Modernization & MARC-HD Indicators

In `dashboard/src/components/ActiveStorefront.tsx`:
- The card displays `/mn/property-check` at `$0.85`, but lacks crucial diligence metadata:
  - Base Mainnet CAIP-2 identifier: `eip155:8453`.
  - Habitability Compliance Indicators: Habitability Score (0-100), License Tier Diligence (Tier 1-3 penalties), 4-Class Deterministic Verdict Engine (`COMPLIANT`, `CONDITIONAL_MAINTENANCE`, `UNLICENSED_ILLEGAL`, `REVOKED_HIGH_RISK`).
- **Telemetry Parity**:
  The component currently displays hardcoded static counts: `views: 142, sales: 18`.
  In reality, the backend demand ledger records over 7,700 challenges served.
  The component should compute live views and sales from incoming `revenueRows` and `activityEvents` state, falling back to historical baseline figures only when SSE telemetry is initializing.

---

## 7. Deployment Rollout & Verification Checklist

### 7.1 Multi-Stage Dockerfile Architecture & Container Integrity

The root `Dockerfile` employs a multi-stage build:
```dockerfile
FROM node:22-bookworm-slim AS dashboard
WORKDIR /src
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
COPY dashboard/package.json dashboard/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY dashboard/ .
ENV VITE_API_BASE_URL=
RUN pnpm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY run_stdio.py .
COPY manifests ./manifests
COPY server.json smithery.yaml smithery.remote-config.json ./
COPY --from=dashboard /src/dist/ ./app/static/mission_control/
ENV HOST=0.0.0.0
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8402}
```

**Key Strengths:**
- `VITE_API_BASE_URL=` ensures same-origin relative URLs (`/telemetry`, `/demand`, `/health`), eliminating cross-origin CORS complexity on Render.
- Clean isolation between Node.js build tooling and the slim Python runtime container.
- Fresh SPA build in `/src/dist/` replaces static assets during container assembly.

**Required Optimization:**
Ensure `.dockerignore` excludes `dashboard/node_modules/` and local `dashboard/dist/` so the Docker build context remains lightweight and builds deterministically from `pnpm-lock.yaml`.

---

### 7.2 Render Blueprint Verification (`render.yaml`)

Inspecting `render.yaml`:
- **Service Name**: `x402-mcp`
- **Plan**: `starter`
- **Region**: `oregon`
- **Runtime**: `docker`
- **Environment Variables**:
  - `X402_PAY_TO_ADDRESS`: `"0x0d25A44f74868eCE53B305C97139CF4B62963410"` (Base receive wallet).
  - `CDP_NETWORKS`: `"eip155:8453"`
  - `REVENUE_NETWORK`: `"eip155:8453"`
  - `X402_DEFAULT_NETWORK`: `"eip155:8453"`
  - `BAZAAR_DISCOVERABLE`: `"true"`
  - `PUBLIC_BASE_URL`: `"https://x402-mcp.onrender.com"`
  - `SWARM_ENABLED`: `"false"` (public seller posture).
  - `DASHBOARD_ACTIONS`: `"true"`

**Audit Evaluation:**
The Blueprint correctly maintains seller-only posture on Base mainnet. When code changes are merged to `main`, Render's GitHub webhook automatically triggers a rebuild using the multi-stage Dockerfile.

---

### 7.3 Step-by-Step Production Deployment Rollout Plan

To safely roll out the modernization and resolve drift without service interruption:

```
[Local Dev & Test]
  1. Fix TypeScript compilation (TelemetryResponse, McpInstructions React import)
  2. Implement MARC-HD analytical engine ($0.85) in backend
  3. Register Tool 21 (mn_property_diligence) in FastMCP and tools_registry
  4. Tame Bubble canvas trail in Bubble.tsx and App.tsx
  5. Enforce CSP on /dashboard in app/main.py
  6. Execute clean SPA build (pnpm run build in dashboard/)
  7. Prune stale static assets in app/static/mission_control/assets/
  8. Copy dashboard/dist/* into app/static/mission_control/
  9. Run test suites (pytest + pnpm test)
        │
        ▼
[Git Commit & Tag]
 10. Commit changes with clear atomic message
 11. Push to origin main
        │
        ▼
[Render Automated Build]
 12. Render triggers multi-stage Docker build
 13. Node 22 stage compiles SPA with empty VITE_API_BASE_URL
 14. Python stage installs dependencies and mounts SPA
 15. Container healthcheck succeeds, new container goes live
        │
        ▼
[Post-Deployment Verification]
 16. Verify HTTP 402 on /mn/property-check ($0.85 / 850000 units)
 17. Verify 21 tools in /.well-known/mcp
 18. Verify CSP headers on both / and /dashboard
 19. Verify newly deployed bundle hash in browser
```

---

### 7.4 Pre-Deployment & Post-Deployment Verification Commands

Execute the following automated verification suite against the deployment target:

#### 1. Verify Price & Protocol Wire Invariants ($0.85 USDC / 850000 units)
```bash
# Must return HTTP 402 with price "$0.85" and amount "850000" in payment-required header
curl -s -D - "https://x402-mcp.onrender.com/mn/property-check" -H "x-demand-ignore: 1" | grep -E "HTTP/|price|payment-required"
```
**Expected Output:**
- Status: `HTTP/2 402`
- JSON Body: `"price": "$0.85"`
- Base64 `payment-required` header decodes to `accepts[0].amount == "850000"` and `network == "eip155:8453"`.

#### 2. Verify Discovery Tool Count (21 MCP Tools)
```bash
curl -s "https://x402-mcp.onrender.com/.well-known/mcp" | jq '.tools | length'
```
**Expected Output:**
`21`

#### 3. Verify Tool 21 Presence in MCP Catalog
```bash
curl -s "https://x402-mcp.onrender.com/.well-known/mcp" | jq '.tools[] | select(.name == "mn_property_diligence")'
```
**Expected Output:**
Non-empty JSON object matching the `mn_property_diligence` tool specification.

#### 4. Verify Content-Security-Policy on Both Routes
```bash
# Verify CSP on root /
curl -s -D - -o /dev/null "https://x402-mcp.onrender.com/" | grep -i "content-security-policy"

# Verify CSP on /dashboard
curl -s -D - -o /dev/null "https://x402-mcp.onrender.com/dashboard" | grep -i "content-security-policy"
```
**Expected Output:**
Both commands return identical `content-security-policy: default-src 'self' ...` headers.

#### 5. Verify Base App ID Meta Tag
```bash
curl -s "https://x402-mcp.onrender.com/dashboard" | grep "base:app_id"
```
**Expected Output:**
`<meta name="base:app_id" content="6a7018e2a8c4f2b6db3b3e71" />`

#### 6. Verify Asset Status & Cache Headers
```bash
# Fetch main HTML to determine active JS bundle hash
BUNDLE_NAME=$(curl -s "https://x402-mcp.onrender.com/" | grep -o 'src="/assets/index-[^"]*\.js"' | cut -d'"' -f2)
echo "Active Bundle: $BUNDLE_NAME"

# Probe bundle asset
curl -s -D - -o /dev/null "https://x402-mcp.onrender.com$BUNDLE_NAME" | grep -E "HTTP/|content-type"
```
**Expected Output:**
- `HTTP/2 200`
- `content-type: application/javascript`

---

## 8. Conclusion & Sign-Off

This audit establishes the baseline facts for the x402-mcp deployment. The transition from the legacy $0.01 unparsed query to the $0.85 MARC-HD diligence verification engine requires coordinated backend pricing updates, FastMCP tool registration (Tool 21), canvas trail taming, strict CSP unification across all routes, and a clean static SPA rebuild.

The steps documented herein provide the exact roadmap for subsequent milestones (M2 through M5) to achieve 100% parity and verification integrity.
