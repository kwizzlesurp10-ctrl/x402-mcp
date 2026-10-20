# x402 Mission Control Admin (Desktop)

Standalone Electron admin shell for the x402-mcp Mission Control dashboard. Operator density is the default: full swarm pipeline, assessment, ledgers, wallet, agent lanes, and MailRail/AgentMail visibility.

This package is **self-contained** — it does not modify `dashboard/` or the API deploy pipeline.

## Quick start

```bash
# Terminal 1 — API
make api

# Terminal 2 — admin UI (Vite dev server on :5174)
make desktop-admin

# Optional — Electron window
cd desktop-admin && pnpm dev:electron
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8402` | Vite dev proxy target for `/api` |
| `VITE_PUBLIC_API_BASE_URL` | (unset) | Optional baked-in API base |
| `VITE_DASHBOARD_ACTIONS` | (unset) | Set `true` to enable seller POST actions in UI |

Use **API settings** in the app to persist a custom base URL (local or production).

## Scripts

```bash
pnpm install
pnpm dev              # Vite @ http://127.0.0.1:5174
pnpm dev:electron     # Vite + Electron
pnpm build            # Production renderer build
pnpm build:electron   # Renderer + electron-builder (dir output)
pnpm test             # vitest
```

See also: [docs/desktop-admin.md](../docs/desktop-admin.md)
