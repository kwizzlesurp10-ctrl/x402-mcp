# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo layout note

This directory is nested inside the user's home, which is itself a git repo tracking `x402-mcp` as a gitlink. Always run git commands from `x402-mcp/`, never the parent. `CHANGES.md` is the manifest of in-scope deltas; parent-repo `git status` output is noise.

## Commands

Windows venv — always use `.venv\Scripts\python.exe` (bash: `.venv/Scripts/python`):

```bash
make up                                          # API (8402) + dashboard (5173) with prefixed logs
make api                                         # uvicorn app.main:app on 127.0.0.1:8402
make dashboard                                   # cd dashboard && pnpm dev
make test                                        # pytest -v + vitest

.venv/Scripts/python -m pytest tests/test_swarm.py::test_name -q   # single test
cd dashboard && pnpm vitest run                  # dashboard tests only
python run_stdio.py                              # MCP stdio transport (Cursor/local)
```

CI (`.github/workflows/ci.yml`) runs pytest on Python 3.12 + vitest on a clean environment.

### Local test failures that are NOT regressions

A configured `.env` (real `EVM_PRIVATE_KEY`) and populated `ledger/*.jsonl` make ~4 tests fail locally that pass in CI: the "missing wallet" tests (`test_mcp_tools`, `test_x402_services`) and `test_ops.py::test_ledger_spend_empty`. `test_docker_evidence.py` / `test_drive_evidence.py` compare previously captured evidence artifacts and go stale whenever tools are added (recapture via `scripts/capture_goal_evidence.py`). Verify a suspected pre-existing failure with `git stash` before assuming your change caused it.

## Architecture

FastAPI + FastMCP server selling x402 (HTTP 402 micropayment) tooling to AI agents, with a commerce overlay, an autonomous buy/compose/resell swarm, and a React "Mission Control" dashboard.

### The tool registry is the single source of truth

`app/tools_registry.py` (`TOOL_SPECS`, `TOOL_COUNT`, `EXPECTED_TOOL_NAMES`) drives the `/.well-known/mcp` manifest, README claims, assessor signals, and the guard tests. **Adding an MCP tool requires touching all of:**

1. `app/mcp_server.py` — `@mcp.tool()` async wrapper delegating to `_execute_tool(name, agent_id, fn)`
2. `app/tools_registry.py` — new `TOOL_SPECS` entry (`requires_env` if the tool needs keys)
3. `README.md` — bump the "N MCP tools" feature line and add a row to the tools table
4. `tests/test_readme.py` — hardcoded count assertion ("N MCP tools" in / "N-1" not in)
5. `tests/test_assessor.py` — `s["mcp_tools"] == N`

`test_manifest.py` and `test_mcp_tools.py` derive from the registry and update automatically.

### Every tool call flows through `_execute_tool`

`app/mcp_server.py::_execute_tool` is the commerce chokepoint: it resolves `agent_id`, enforces quota/rate-limit *before* execution (`app/commerce.py`), appends the `meta` envelope (quota remaining, tier, upgrade URL) to every response, and emits an ops event. Tools return JSON strings. New tools must not bypass it.

### Commerce overlay and revenue paths

`app/commerce.py`: free tier (500 calls/mo, 10/min), pro tier, per-use tool credits consumed when quota is exhausted. Three revenue paths: pro upgrade and tool credits via x402 verify+settle (`app/x402_services.py`), and the Stripe rail (`app/stripe_payments.py`, `POST /stripe/checkout` + webhook). Settlement is hardened: settled-gating, idempotency, challenge binding.

### Swarm agency (`app/swarm/`)

Buy-compose-resell pipeline, gated by `SWARM_ENABLED`: **scout** discovers upstream x402 services → **warden** enforces `ledger/policy.json` spend caps → **treasurer** pays (`pay_and_fetch`, sole spender) → **archivist** composes a priced composite → **sovereign** reprices for target LTV:CAC and margin floor → **merchant** lists it; `settle_composite_sale` records revenue. `assessor.py` scores profit routes from real repo signals — growth/outreach/financial actions are deliberately HUMAN-GATED. Composites are also served as payable 402 endpoints. The `.claude/agents/` subagent definitions mirror these roles for operating the server on a cost ladder (free tools → cache → capped mainnet; see `docs/agent-ops.md`).

### Ledger (`ledger/`)

`policy.json` (committed) holds caps and allow/deny lists. `spend.jsonl`, `revenue.jsonl`, and `cache/` are git-ignored records of real payments — never commit them, never reset them casually.

### Mission Control / ops events

`app/ops_events.py` is a fire-and-forget in-memory event bus: **emit functions must never raise into tool execution**. Everything (tool calls, swarm phase steps, alerts) rides the single `/events` SSE stream as `type: "tool"` events differentiated by `meta` keys — the dashboard's agent lanes match on `agent_id` prefixes. Read-only dashboard endpoints in `app/main.py`: `/stats`, `/doctor`, `/wallet`, `/ledger/{name}`, `/swarm/*`, `/pulse`, `/security`. Dashboard POST actions are disabled unless `DASHBOARD_ACTIONS=true` (CORS is locked to the Vite dev origin).

### Security seams

- `app/ssrf_guard.py` validates all user-supplied probe URLs; `app/probe_rate_limit.py` rate-limits probes
- `app/keyprovider.py` is the pluggable key seam (`KEY_PROVIDER`); env-var keys log a deprecation warning
- `/wallet` and error responses expose public addresses/generic messages only — never key material or exception internals

### Config

All settings are env-driven via `app/config.py` (pydantic-settings, `.env` loaded, never committed). Networks use CAIP-2 ids (`eip155:8453` Base mainnet, `eip155:84532` Base Sepolia); Solana (SVM) is registered for multi-chain selling and requires `solana<0.40`.

### Data honesty convention

Synthesized intelligence products (`app/pulse.py`, assessor) compute from real, inspectable sources (RPC, spot APIs, repo state) — no mocked or marketing numbers. Follow this when adding data products.
