# Claude Code Handoff v2 — "x402 Mission Control" (post-observer audit)

Supersedes UI-HANDOFF.md. Same stack (Vite + React 19 + TS, pnpm, FastAPI additions), same fintech-terminal design language. This version merges the first-run observer audit: the v1 spec assumed an operator who already understands x402; v2 must carry a greenhorn from clone → running → first paid fetch → first revenue → net-positive without leaving the dashboard.

## Product principle

Every panel must answer three questions for someone who has never seen x402: **what is this**, **what do I do next**, and **did it work**. Pro density is preserved behind a mode switch — never dumb the terminal down, layer the guidance on.

## P0 — Blocks a greenhorn entirely

1. **One-command boot.** `make up` (and `pnpm mission-control`) starts FastAPI (keyless instance) + dashboard concurrently with prefixed logs. Also add `docker compose up` covering server + dashboard. Three terminals is where greenhorns quit.
2. **First-run setup wizard.** Dashboard detects incomplete config via a `/stats` config echo (`has_pay_to`, `has_buyer_key`, `redis_mode`, `network`) and renders a checklist overlay instead of an empty dashboard:
   - Server reachable ✓/✗ (with the exact uvicorn command to fix)
   - Receive wallet set (`X402_PAY_TO_ADDRESS`) — with "don't have a wallet?" link path
   - Vault key set (for paying) — clearly marked OPTIONAL, testnet-only guidance
   - Testnet USDC funded — deep link to the Base Sepolia CDP faucet, shows vault balance
   - Each item has a copy-paste fix. Wizard dismissible; re-openable from header.
3. **Doctor command.** `python -m app.doctor` — validates .env, checks `.mcp.json` server keys match agent tool prefixes, pings facilitator + discovery URLs, reads testnet USDC balance, prints PASS/FAIL with fixes. Wizard consumes the same checks via `/doctor` endpoint.
4. **Demo mode.** Header toggle seeds the UI with realistic fake data (spend rows, revenue, activity stream replay) so every panel is legible and the product is testable with zero wallet, zero payments. Clearly watermarked `DEMO`. This is also the sales/screenshot mode.
5. **Actionable empty states.** Zero states prescribe the next action with a copy-paste command or one-click (in demo/playground): quota gauge empty → "No calls yet — run your first free discovery"; spend table empty → "Nothing spent. Good. Here's how to make your first $0.00 testnet fetch →".
6. **Persistence banner.** When `redis_mode: "memory"`, a persistent amber system banner: "In-memory store — quota, tiers, and credits reset on restart. Set REDIS_URL before selling to real buyers." Non-dismissible once any revenue row exists; escalates red.
7. **Actionable error states.** Every failure renders what happened / why / how to fix, in plain language, with the command. SSE dead → "Dashboard can't reach the server at :8402 — is it running? `make up`". Never a blank panel, never a raw stack trace by default (expandable for pros).

## P1 — Major friction on the running→profiting path

8. **Probe-from-URL in the 402 Inspector.** Greenhorns have no base64 to paste. Add keyless backend proxy `GET /probe?url=&method=` (wraps `get_payment_requirements`, no wallet, rate-limited, SSRF-guarded: http(s) only, no link-local/private ranges). Inspector becomes: paste URL → decoded tree with amount (human USDC + raw atomic on hover), network chip, payTo, scheme highlighted → "copy as scout report" button. Keep the raw-base64 paste tab for pros.
9. **Wallet panel.** Shows vault **public address only**, Sepolia + mainnet USDC balances via public RPC read, faucet deep link, low-balance warning at < 5 testnet payments' worth. Never displays or requests private keys; panel copy explicitly says keys stay in server env.
10. **Mission progress tracker.** The running→profiting funnel as a compact checklist in the header drawer: Server up → Dashboard connected → First discovery → First probe → Testnet funded → First paid fetch → First seller config → First verified revenue → **Net ≥ 0**. Each step deep-links to the relevant panel/instruction. Completion state from `/stats` + ledgers (derive, don't store server-side); localStorage caches dismissal only.
11. **"Sell something" wizard.** Guided seller flow: price + network (defaults Sepolia, mainnet gated behind an "I understand this is real money" confirm) + description → shows the `build_seller_requirements` invocation to run (or executes via a keyless `POST /seller/requirements` if you promote the dashboard past read-only — acceptable; it moves no funds) → outputs the requirements JSON + a minimal FastAPI 402-gate snippet the user can deploy → break-even math: "At $0.01/call, 37 verified calls covers this month's spend."
12. **Break-even visualization on the hero stat.** Net-position numeral gets a progress bar to $0 when negative, with "what closes the gap" hint (calls-to-break-even at current default price). When positive: "self-sustaining for N days" streak.
13. **Skill-adaptive density: Guided / Standard / Operator.** Guided = larger targets, plain-language labels ("Payment demanded: $0.01" vs "maxAmountRequired: 10000"), glossary tooltips on every jargon term (402, facilitator, settle, atomic units, quota, meta envelope, facilitator). Operator = v1 density, no tooltips, cmd+K palette. Standard = default middle. Mode persists locally.
14. **Glossary tooltips + "what am I looking at" per panel.** Small `?` per panel opens a 3-sentence explainer with one example. Content lives in a single `glossary.ts` so agents/docs can share it.

## P2 — Fluidity & pro polish

15. **cmd+K palette:** jump to panel, copy addresses, toggle demo/density, filter ledgers by network/agent.
16. **Copy affordances** on every hash, address, and amount (click-to-copy with checkmark micro-feedback).
17. **Relative timestamps** ("2m ago") with absolute on hover; ledger export as CSV/JSONL download.
18. **Accessibility:** every status dot paired with a text label (color-blind safe), full keyboard nav, visible focus rings, `prefers-reduced-motion` kills count-ups and slide-ins.
19. **Responsive summary view** ≤ 768px: hero stats + activity stream + mission progress only.
20. **Confirm pattern for any future money-adjacent action:** plain-consequence copy ("This spends real USDC on Base mainnet — up to $0.01"), typed network name required for mainnet, never for testnet.
21. **Counter-reset grace:** stats legally drop to zero on server restart (in-memory store) — animate down as instant snap with a one-line toast "Server restarted — in-memory counters reset," linking the persistence banner.
22. **Onboarding replay:** "Show me around" replays the wizard + a 5-step spotlight tour. Never auto-plays twice.

## Backend additions (delta from v1)

- `/stats` gains the config echo fields (`has_pay_to`, `has_buyer_key`, `redis_mode`, network, prices).
- `GET /doctor` — machine-readable checks powering the wizard.
- `GET /probe?url=&method=` — keyless 402 probe proxy (SSRF-guarded, 10/min per IP).
- `POST /seller/requirements` — keyless wrapper on build_seller_requirements (optional; gate behind `DASHBOARD_ACTIONS=true` env flag, default off, keeping pure read-only deployable).
- `GET /wallet` — public address + RPC balance reads (no key material ever serialized).
- SSE `/events` unchanged; add heartbeat every 15s so the live-dot is truthful.

## Unchanged from v1

Design tokens, fintech-terminal restraint, JetBrains Mono tabular-nums for all numerals, ledger table specs, BaseScan linking, virtualized lists, Vitest coverage on decode/format utils, pnpm version pinning in CI (`packageManager` field + action config), integer atomic-unit math formatted at render.

Deliverables: `dashboard/` app, backend diff, `make up` + compose file, `app/doctor.py`, updated README quickstart reduced to three commands, all green under `pnpm vitest run` and `pytest`.
