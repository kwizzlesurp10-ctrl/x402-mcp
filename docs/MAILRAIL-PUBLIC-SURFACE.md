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
| MCP `mailrail.send` / `mailrail.inbound` / `mailrail.status` | No | Not registered on the public FastMCP server |
| `POST /mailrail/inbound` | No | `Authorization: Bearer $OPERATOR_TOKEN` (fail closed if token unset) |
| `GET /mailrail/ledger` / `inbox` / `stats` | No | Same bearer gate |
| `GET /mailrail/health` | Yes, readiness only | No message bodies; no admin recipient |
| Internal `mailrail.send_agent_mail` from settlement code | Yes (server-side) | Not an HTTP/MCP public tool |

Public Smithery catalog is x402 / commerce / swarm / pulse / ops / city only.

Operator MailRail stays in-process for receipts. External ingest requires `OPERATOR_TOKEN`.
