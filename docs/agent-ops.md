# x402-MCP Agent Ops — Cost-Effective-to-Free Operating Group

Five Claude Code subagents that operate `x402-mcp` on a strict cost ladder: free tools first, cache second, testnet third, capped mainnet last, seller + Stripe revenue offsetting spend.

Agent definitions: `.claude/agents/`  
Ledger policy: `ledger/policy.json`  
MCP wiring example: `.mcp.json.example`

## Two-Instance Topology

```
Instance A — "free" (no EVM_PRIVATE_KEY)          Instance B — "vault" (EVM_PRIVATE_KEY set)
  port 8402 or stdio                                 stdio only, testnet key by default
  scout, warden, archivist, merchant                 treasurer ONLY
```

Copy `.mcp.json.example` → `.mcp.json` (git-ignored). Keep keys in `.env`, never commit.

## The Agents

| Agent | Model | Instance | Job |
|---|---|---|---|
| `x402-scout` | haiku | A | Discover + probe. Never pays. |
| `x402-archivist` | haiku | A | Cache layer. Never pay twice. |
| `x402-warden` | sonnet | A | Budget policy. Approves/denies payments. |
| `x402-treasurer` | sonnet | B | Sole `pay_and_fetch` executor. |
| `x402-merchant` | sonnet | A | Revenue — x402 seller + Stripe checkout. |

## Cost Ladder

1. **$0 keyless tools** — discover, probe, networks, verify (no wallet)
2. **Cache-first** — archivist `ledger/cache/`
3. **Capped mainnet** — warden enforces `ledger/policy.json` caps
4. **Revenue offset** — merchant + Stripe; goal net ≥ 0

## Ledger (`ledger/`)

- `policy.json` — caps, networks, allow/deny (committed)
- `spend.jsonl` — treasurer payments (git-ignored)
- `revenue.jsonl` — merchant verifications (git-ignored)
- `cache/` — archivist store (git-ignored)

## Mission Control API

Read-only ops endpoints for the dashboard handoff ([UI-HANDOFF.md](UI-HANDOFF.md)):

| Endpoint | Purpose |
|----------|---------|
| `GET /stats` | Quota store snapshot |
| `GET /events` | SSE tool invocation stream |
| `GET /ledger/spend` | Spend ledger rows |
| `GET /ledger/revenue` | Revenue ledger rows |

## Flow

```
task → scout → archivist (cache) → warden (APPROVE/DENY) → treasurer (vault)
     → archivist (store) → warden (ledger)
merchant / Stripe run independently for revenue
```