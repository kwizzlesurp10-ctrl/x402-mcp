# Change control — add-only checkpoint

**Frozen healthy snapshot:** git tag `healthy-2026-09-16` (the storefront as it was when this lock landed).

This repo is a working paid seller. Other agents must not "clean up", refactor, or delete code that already exists. One bad rewrite of `app/main.py` or a price in `app/config.py` can break discovery or settlement.

## What an agent may do without asking

- **Add** new files (tests, docs, scripts, workflows).
- Read anything. Run tests. Probe live endpoints with `x-demand-ignore`.

## What is blocked until you click Approve

Any **modify, delete, rename, copy, or type-change** of a file that already exists on the base branch (`master` / the PR base). That includes:

- `app/`, `dashboard/`, `render.yaml`, `ledger/policy.json`, prices, CI, this document, the guard itself
- "move to a better name" (git `R`) — it deletes the old path
- a new file plus an edit of an old file in the same PR — still a mutation

Bypass is **not** an env var (`OPERATOR_APPROVED` is ignored). Agents can set env vars.

## How a mutation actually lands

1. Open a **pull request**. Direct pushes to `master` are blocked by the repository ruleset.
2. Workflow `add-only` classifies the diff.
3. If it is add-only, check `change-control` goes green.
4. If it mutates existing files:
   - a `change-control` issue is opened and assigned to `kwizzlesurp10-ctrl`
   - job `operator-approve` waits on GitHub Environment **`operator-approve`**
   - you get a 15-minute wait, then click **Approve** (or Reject) in the Actions UI
5. Merge only after `change-control` is green.

Environment URL: `https://github.com/kwizzlesurp10-ctrl/x402-mcp/settings/environments`

## Rollback

```
git fetch origin tag healthy-2026-09-16
git checkout healthy-2026-09-16
```

That tag is the pre-lock storefront. To restore files from it onto a branch without rewriting history blindly, checkout individual paths.

## Local check (optional speed bump)

```
.venv\Scripts\python.exe scripts/add_only_guard.py --base origin/master
```

Exit 1 means existing files changed. `--no-verify` on commit does not help you on GitHub — CI still classifies the range `BEFORE...SHA`.

## Honesty about same-account agents

Agents in this workspace often act as `kwizzlesurp10-ctrl`. They can:

- self-approve a CODEOWNERS review
- call the pending-deployment API **if** they have the owner token

The Environment click + 15-minute wait is a cancel window and a notification, not cryptography. Strongest upgrade: add a **second GitHub user** as the only Environment reviewer and never give that token to agents.

Do not put spend keys on the public box. Do not run `scripts/settle_once.py` from an agent.
