# MailRail public-surface decision

MailRail is an **operator communication rail** (settlement receipts, alerts, inbound postmaster). It is **not** a public x402 product.

## What was exposed

Unauthenticated clients could:

- Call MCP `mailrail.send` and send email/webhooks using the host's Resend/SMTP/webhook credentials.
- Call MCP `mailrail.inbound` and write into the inbox ledger.
- `GET /mailrail/ledger` and `GET /mailrail/inbox` and dump those messages.
- `POST /mailrail/inbound` without a token.

That is open-relay + inbox disclosure on a public seller host. **Do not list these on Smithery.**

## Decision

| Surface | Public? | Gate |
|---|---|---|
| MCP `mailrail.send` / `mailrail.inbound` / `mailrail.status` | No | Not registered on the public FastMCP server. In-process callers must be the postmaster or the helper returns `forbidden` before any ledger write. |
| `POST /mailrail/inbound` | No | `Authorization: Bearer $OPERATOR_TOKEN` and `X-Agent-Id: x402-mailrail-postmaster`. Missing token is 401. Wrong or missing agent is 403. |
| `GET /mailrail/ledger` / `inbox` / `stats` | No | Same postmaster gate |
| `GET /agent/mailrail` | Card only (`public: false`) | No token. No message bodies. |
| `GET /mailrail/health` | Yes, readiness only | `enabled` and `provider`. No admin recipient, from-address, or key flags. |
| Internal `mailrail.send_agent_mail` from settlement code | Yes (server-side) | Not an HTTP/MCP public tool |

The seller sets `MAILRAIL_ENABLED=true` and `MAILRAIL_PROVIDER=mock`. Mock records mail and does not call Resend or a webhook. Do not put `MAILRAIL_API_KEY`, `MAILRAIL_WEBHOOK_URL`, or `GITHUB_TOKEN` in `render.yaml`.

Public Smithery catalog is x402 / commerce / swarm / pulse / ops / city only.

Operator MailRail stays in-process for receipts. External ingest requires `OPERATOR_TOKEN` and the postmaster agent id.
