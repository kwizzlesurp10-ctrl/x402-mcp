# Claude Code Handoff — "x402 Mission Control" Dashboard

Self-contained prompt. Paste into Claude Code from the `x402-mcp` repo root.

---

Build a read-only ops dashboard for this repo's x402 MCP server. Stack: **Vite + React 19 + TypeScript**, pnpm, single-page, deployable to Vercel as `dashboard/`. Backend: add a small read-only stats surface to the existing FastAPI app (`app/main.py`) — do not touch the MCP tool layer.

## Backend additions (FastAPI)

1. `GET /stats` — JSON snapshot from the quota store: per-agent `{agent_id, tier, calls_this_month, quota_remaining, rate_limit_remaining, tool_credits_remaining}` plus config echoes (tier limits, prices, default network). Add a `snapshot()` method to `InMemoryQuotaStore` rather than reaching into privates.
2. `GET /events` — SSE stream emitting one event per tool invocation `{ts, tool, agent_id, meta}`. Hook it via a lightweight callback in `_execute_tool` (fire-and-forget; never block or fail a tool call because the dashboard is down).
3. CORS for the dashboard origin only. No auth for now, but bind assumption is localhost/tailnet — put a `# TODO auth before public exposure` marker.
4. Serve nothing else new. The dashboard reads `ledger/*.jsonl` via a `GET /ledger/{spend|revenue}` endpoint that streams the jsonl parsed to JSON arrays (cap 1000 rows, newest first).

## Layout (desktop-first, 12-col grid, single screen, no routing)

```
┌─ Header: wordmark "x402 // mission control" · network chip · tier badge · live dot ─┐
├─ Row 1: [Quota burndown gauge] [Rate-limit sparkline] [Net position stat] [USDC saved by cache stat]
├─ Row 2 (2/3): Live activity stream (SSE) — one row per tool call, agent-colored
│  Row 2 (1/3): Agent lanes — scout/warden/treasurer/archivist/merchant cards w/ last action + calls today
├─ Row 3 (1/2): Spend ledger table            Row 3 (1/2): Revenue ledger table
└─ Row 4: 402 Inspector — URL input → calls GET /probe? NO — dashboard is read-only; instead paste a
   base64 PAYMENT-REQUIRED blob → client-side decode → pretty tree with amount/network/payTo highlighted
```

## Component specifics

- **Quota burndown gauge:** radial, `calls_this_month / limit`, warning ring color shift at 80% (matches `quota_warning`).
- **Net position stat:** `Σ revenue − Σ mainnet spend`, big tabular numeral, green when ≥ 0 with a subtle "self-sustaining" label — this is the product's whole thesis, give it the hero spot.
- **Ledger tables:** monospace amounts right-aligned, network as colored chip (Base mainnet vs Sepolia), tx hash truncated middle (`0x12ab…9f`) linking to basescan.org / sepolia.basescan.org, settle status as dot (green settled / amber unconfirmed / red failed). Sortable by ts/amount. No pagination UI — virtualized list.
- **Activity stream:** newest on top, max 200 rows in memory, each row `[hh:mm:ss] [agent chip] tool_name → quota_remaining`. Auto-scroll with a "paused on hover" affordance.
- **402 Inspector:** textarea → `atob` → JSON.parse → collapsible tree. Highlight `maxAmountRequired`/amount fields converted to human USDC (÷1e6), `payTo`, `network`. Graceful error state for malformed base64.
- **Empty states everywhere** — this dashboard will often boot against a fresh in-memory store; every panel needs a designed zero state, not a blank.

## Design language — "fintech terminal"

- Dark base `#0B0F14`, panel `#11161D`, hairline borders `#1E2630`, radius 10px, 8px spacing grid.
- Type: Inter for UI, **JetBrains Mono with `font-variant-numeric: tabular-nums`** for every number, amount, hash, and timestamp. Numbers never jitter.
- Accents: USDC blue `#2775CA` (amounts), Base blue `#0052FF` (mainnet chip), amber `#F5A623` (testnet chip + warnings), green `#2FBF71` (settled/net-positive), red `#E5484D` (denied/failed). One accent per element — no gradients, no glow. Restraint is what reads "pro."
- Motion: 150ms ease-out on value changes only (count-up on stats, row slide-in on stream). Nothing loops.
- Status via dots and chips, never modals or toasts for routine events.
- Light mode: skip it. Optional later.

## Gotchas

- `pnpm` everywhere; pin the pnpm version in any GitHub Actions workflow you add (`packageManager` field in package.json AND the action config — this repo family has been bitten by the missing pin before).
- SSE reconnect with backoff; the stream dying must degrade to polling `/stats` every 10s, indicated by the header live-dot going amber.
- All USDC math client-side in integer atomic units; format at render only.
- The in-memory store means `/stats` can legitimately reset to zero mid-session — handle counters going *down* without animation glitches.
- Vitest for the decode utils (base64 402 parsing, atomic-unit formatting) at minimum.

Deliverables: `dashboard/` app, backend diff to `app/main.py` + `app/commerce.py` (snapshot method), updated README section, all tests green with `pnpm vitest run` and `pytest`.