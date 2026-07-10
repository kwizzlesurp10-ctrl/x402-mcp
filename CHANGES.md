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
- `run_stdio.py` — MCP stdio entry
- `docs/runbook.md`, `docs/architecture.md`

## Revenue paths (criteria 3)

1. **Pro tier** — `get_pro_upgrade_requirements` → pay → `activate_pro_tier` (verify + settle)
2. **Per-use credits** — `get_tool_credits_requirements` → pay → `purchase_tool_credits` (verify + settle); credits consumed when monthly quota exceeded
3. **HTTP upgrade** — `GET /upgrade` documents payment flow (no 404)

## 2026-07-10 — hermetic tests + operator dashboard

- **Fixed all 17 failing tests** (root cause: `x402` SDK not installed in the active env → `pip install -e ".[dev]"`).
- **Hermetic test backend** (`tests/conftest.py`): session-scoped mock x402 facilitator (`/facilitator/supported`) + CDP discovery (`/discovery/resources`) on localhost. Wired via `X402_FACILITATOR_URL`/`CDP_DISCOVERY_URL` env vars (inherited by stdio subprocess tests) and by patching the in-process `settings` singleton. `X402_LIVE_TESTS=1` bypasses the mock.
- `test_get_payment_requirements_public_url` now uses the local `probe_402_url` fixture instead of httpbin.org.
- **Operator dashboard** (`app/dashboard.py`, route `GET /dashboard`, `/` redirects there): fintech-terminal UI polling `/health`, `/quota/{agent}`, `/.well-known/mcp`, `/upgrade` every 5s. Block-character quota meters, 10-tool matrix, revenue paths, live event tape. Inline CSS/JS, no build step.
- New `tests/test_dashboard.py` (4 tests) keeps the UI under test discipline.
- Result: **54 passed, 0 failed** (20 evidence tests skip by design until `capture_goal_evidence` artifacts exist).
