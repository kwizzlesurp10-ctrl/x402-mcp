# Desktop Admin — Mission Control

The `desktop-admin/` package is a sibling Electron app that reuses Mission Control React components from `dashboard/` via Vite path aliases. It targets operators who want a dedicated window with **operator density** locked on and MailRail visibility built in.

## Architecture

```
desktop-admin/
  electron/          # Electron main + preload (contextIsolation)
  src/
    App.tsx          # Admin layout (operator panels always on)
    api/client.ts    # Dynamic API base + MailRail endpoints
    components/      # AdminHeader, MailRailPanel, SettingsDialog
  vite.config.ts     # Aliases ../dashboard/src, proxies /api in dev
```

- **Renderer**: React 19 + Vite 6 (port **5174**, separate from dashboard **5173**)
- **Shell**: Electron 34 (`electron/main.cjs`, optional system tray in production builds)
- **Shared UI**: `@dashboard/*` imports resolve to `../dashboard/src/*`; `api/client` is overridden for runtime API base + MailRail routes

## Run locally

```bash
make api                 # 127.0.0.1:8402
make desktop-admin       # Vite admin UI
# or
cd desktop-admin && pnpm dev:electron
```

## API base URL

| Mode | Default base | Notes |
| --- | --- | --- |
| Dev (Vite) | `/api` | Proxied to `VITE_API_PROXY_TARGET` |
| Electron prod | `http://127.0.0.1:8402` | Change via in-app **API settings** |
| Custom | user setting | Persisted in `localStorage` |

## Operator features

- Swarm assessment + human-gated backlog (collapsed in standard dashboard, expanded in operator — always operator here)
- Swarm activity pipeline + agent lanes
- Active storefront / composites
- Stats, wallet, OS health, pulse
- Spend + revenue ledgers with CSV/JSONL export
- 402 inspector
- MailRail outbox/inbox panel (`/mailrail/*`)
- Seller wizard (POST gated by `DASHBOARD_ACTIONS` on **server** and `VITE_DASHBOARD_ACTIONS` in UI)

## Build

```bash
cd desktop-admin
pnpm install
pnpm build            # renderer only
pnpm build:electron   # renderer + unpacked Electron app in release/
```

## Tests

```bash
cd desktop-admin && pnpm test
```

CI runs vitest for `dashboard/` today; add `desktop-admin` to CI when the lockfile is committed.

## Reference repo note

The requested reference **"x402 Oracles Dashboard & AgentMail"** was not found as a public repo under `kwizzlesurp10-ctrl`. The closest sibling is [`x402orcle`](https://github.com/kwizzlesurp10-ctrl/x402orcle) (Next.js + MCP, no Electron). This desktop admin follows the **Electron + Vite + React** pattern common for operator dashboards and wires MailRail using existing `x402-mcp` HTTP routes.
