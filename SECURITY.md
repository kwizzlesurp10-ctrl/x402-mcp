# Security Policy

## Supported Versions

We actively support the latest minor release of x402-mcp with security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

Only the current 0.1.x line receives security patches. Older pre-release or untagged commits are unsupported.

## Reporting a Vulnerability

**Do not open public GitHub issues or pull requests for security vulnerabilities.**

### Preferred Reporting Channels

1. **GitHub Private Vulnerability Reporting** (recommended if enabled for this repository): Use the "Report a vulnerability" button on the Security tab.
2. **Email**: Send a detailed report to `kwizzlesurp10@gmail.com` with the subject line `[SECURITY] x402-mcp`.

Include as much detail as possible:
- Description of the vulnerability and its impact
- Steps to reproduce (PoC if available)
- Affected versions / commit SHA
- Suggested remediation (optional)

### Response Timeline

- **Acknowledgment**: Within 48 hours of receipt
- **Status updates**: At least every 7 days while the report is under investigation
- **Resolution target**: Critical issues within 14 days; high/medium within 30 days where feasible

### What to Expect

- **Accepted**: We will confirm the issue, develop and test a fix, coordinate disclosure timing with you, and credit you in the advisory / release notes if you wish (anonymous reporting is fully supported).
- **Declined**: We will provide a clear explanation (e.g., not reproducible, out of scope, already fixed, or accepted risk). You may request a second review.

### Scope Notes

This policy covers the x402-mcp codebase, its dependencies as used in the project, the seller storefront endpoints, payment verification/settlement paths, quota and Redis stores, and the operator dashboard. Issues in upstream x402 SDKs, Coinbase CDP, or third-party facilitators should be reported to their respective maintainers; we will still assist in triage when relevant.

MailRail send/inbound and message ledgers are **operator-only**. They are not public MCP tools. HTTP ingest/ledger/inbox/stats require `Authorization: Bearer $OPERATOR_TOKEN` and fail closed if the token is unset. See [docs/MAILRAIL-PUBLIC-SURFACE.md](docs/MAILRAIL-PUBLIC-SURFACE.md).

Thank you for helping keep x402-mcp and the agent commerce ecosystem secure.

## Operator surfaces and agent identity

`OPERATOR_TOKEN` (sent as `Authorization: Bearer …`, compared in constant time)
is the single, **required** operator credential. Callers without it see
`/stats` aggregates only (no agent ids), and `/events` and `/swarm/runs`
redact agent ids. A wrong or missing bearer on `/quota/{agent_id}`,
`/pulse/publish`, `/swarm/run` or MailRail gets 401.

If the server has no `OPERATOR_TOKEN` configured at all, those operator
routes return **503 `operator_surface_disabled`** (never open) and startup
logs an error. Set `REQUIRE_OPERATOR_TOKEN=true` to make the process refuse
to start without it. Use a long random value (>= 24 chars; e.g.
`openssl rand -hex 32`). The token is never rendered into HTML.


## Change control for CODEOWNERS and workflows

`.github/CODEOWNERS`, everything under `.github/workflows/`, and
`scripts/add_only_guard.py` decide who can change this repo and what CI is
allowed to do. Changes to them need more than one click from the owner
account:

- **Second human reviewer, or a hardware key.** A change to these paths must
  be approved by a second human who is not the PR author. If no second
  person is available, the approving account must sign in with a hardware
  security key (FIDO2/WebAuthn, e.g. a YubiKey) only. Remove TOTP/SMS
  fallbacks from that account.
- **Agents never approve these.** Automation and AI agents often run with
  the owner's token. A PR approved, environment-approved, or merged by that
  token proves nothing about a human decision, and GitHub can't tell the
  difference. Use a separate fine-grained token for agents that has no
  `administration`, `workflows`, or environment-approval rights.
- **The 15-minute wait is only a notification.** The `operator-approve`
  environment's wait timer and its `change-control` issue tell the owner
  that a change is pending. They are not a cryptographic control. Anyone
  holding the owner token can approve the pending deployment through the
  API once the timer runs out. Treat the issue as an alarm that needs a
  human to look at it, and keep the real gate in branch protection.
- **Branch protection on `master`:** require PRs; require review from
  Code Owners; require approval of the most recent push; dismiss stale
  approvals; require the `change-control` check; disallow force-push and
  deletion; include administrators.
