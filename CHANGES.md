# x402-mcp project changes (isolated scope)

This file documents deltas **only** within `C:\Users\Keith\x402-mcp\`.
The parent workspace git root (`C:\Users\Keith`) contains unrelated untracked files;
use this manifest for goal verification instead of repo-wide `git status`.

## Application (`app/`)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI: `/health`, `/.well-known/mcp`, `/upgrade`, `/quota/{id}`, MCP mount |
| `mcp_server.py` | 10 MCP tools, preemptive quota via `_execute_tool(resolved)` |
| `x402_services.py` | x402 SDK buyer/seller flows, verify+settle revenue paths |
| `commerce.py` | Tiers, quota, rate limits, tool credits, meta envelope |
| `config.py` | Env-based settings (wallet, facilitator, tier prices) |
| `models.py` | Pydantic tool I/O + `ResponseMeta` |
| `manifest.py` | `/.well-known/mcp` tier + tool catalog |

## Tests (`tests/`)

- `test_commerce.py` — quota, 429, credits, meta
- `test_manifest.py` — HTTP endpoints including `/upgrade`
- `test_mcp_tools.py` — MCP wrapper, agent_id consistency, pro activation
- `test_mcp_stdio.py` — stdio `call_tool` transport for 4 tools
- `test_x402_services.py` — discovery, probe, wallet guard
- `test_pay_and_fetch_e2e.py` — mocked pay-and-fetch E2E

## Scripts & docs

- `scripts/verify_goal.py` — verification plan evidence capture
- `scripts/vercel_connect_token.py` — Vercel Connect token for the `huggingface.co/x402-mcp` MCP connector (OIDC env or CLI fallback), `--verify` smoke-tests tools/list
- `run_stdio.py` — MCP stdio entry
- `docs/runbook.md`, `docs/architecture.md`
- `docs/swarm/PROFIT_ORCHESTRATOR.md` — operator-supplied profitability swarm spec v1.0 (2026-07-16)

## Swarm pipeline fixes (2026-07-16)

- `app/x402_services.py::parse_amount_atomic` — tolerant Bazaar `accepts[].amount` parsing (decimal-USDC strings like `"0.016"` no longer crash discovery); used by the discovery price filter and `roles.py::_parse_accepts`
- `app/swarm/roles.py::treasurer_buy` — POST fallback on 404/405 (no 402 challenge issued, so nothing paid twice); unlocked the first fully settled buy→compose→list cycles
- `app/config.py` — Pulse list price $8.00 → $0.25 (operator-approved reprice toward the ~$0.30 ecosystem average per call)

## Revenue paths (criteria 3)

1. **Pro tier** — `get_pro_upgrade_requirements` → pay → `activate_pro_tier` (verify + settle)
2. **Per-use credits** — `get_tool_credits_requirements` → pay → `purchase_tool_credits` (verify + settle); credits consumed when monthly quota exceeded
3. **HTTP upgrade** — `GET /upgrade` documents payment flow (no 404)