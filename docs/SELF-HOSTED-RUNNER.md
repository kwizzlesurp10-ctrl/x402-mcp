# Self-hosted runners

GitHub-hosted Actions minutes are locked while the account has a failed
payment, so most workflows run on repo-level self-hosted runners:
`runs-on: [self-hosted, linux, x64]`. Whichever matching runner is online picks
up the job.

| Runner | Labels | Role |
|---|---|---|
| Keith's home PC | `self-hosted, linux, x64, keef-pc` | primary |
| `box-runner` | `self-hosted, linux, x64, box` | backup |

Jobs must stay portable across both machines: get toolchains from
`actions/setup-python`, `pnpm/action-setup`, etc., never from machine-specific
paths. `gh`, `git`, `curl`, `jq`, `python3` and `node`/`npx` must be on the
runner's PATH (sale/task/thread watch and add-only use them directly). GitHub
`ubuntu-latest` images ship the same CLI surface for workflows that fall back.

Note: `actions/setup-python` only ships Ubuntu builds. On non-Ubuntu hosts
(the box is Debian 13) pre-seed the runner tool cache once, e.g.
`uv python install 3.12` and copy it to
`<runner>/_work/_tool/Python/<ver>/x64` + touch `x64.complete`.

## Automatic fallback to GitHub-hosted

When every self-hosted runner is offline, alert and housekeeping workflows would
otherwise sit queued for hours. They now call the reusable workflow
`.github/workflows/runner-pick.yml` first:

1. A tiny job on `ubuntu-latest` calls
   `GET /repos/{owner}/{repo}/actions/runners`.
2. If any runner with the `self-hosted` label is `online` or `busy`, later jobs
   use `[self-hosted, linux, x64]` (same as before).
3. If none are connected, or the API call fails, later jobs use `ubuntu-latest`
   so sales, outreach, 0xWork, and change-control alerts still fire.

Caller pattern:

```yaml
jobs:
  pick-runner:
    uses: ./.github/workflows/runner-pick.yml
    secrets: inherit

  watch:
    needs: pick-runner
    runs-on: ${{ fromJSON(needs.pick-runner.outputs.runner) }}
```

### Workflows with fallback

| Workflow | Schedule / trigger | Fallback? |
|---|---|---|
| `sale-watch.yml` | every 30 min | yes |
| `task-watch.yml` | every 30 min | yes |
| `thread-watch.yml` | every 30 min | yes |
| `change-control-sweep.yml` | daily 04:17 UTC | yes |
| `add-only.yml` | push / PR | yes |
| `mcp-registry-publish.yml` | tag / manual | yes |
| `storefront-monitor.yml` | every 15 min | always `ubuntu-latest` |
| `ci.yml` | push / PR | **no** — self-hosted only (heavy; queues when offline) |

Each fallback workflow pays for one extra `ubuntu-latest` picker job per run
(usually &lt;30 seconds). With self-hosted offline all day, expect roughly
**~4 hosted hours/day** from the three 30-minute watchers plus the daily sweep
(~1–3 min per watch run, dominated by `task-watch`’s `npx @0xwork/cli`).
`add-only` and `mcp-registry-publish` add minutes only when they actually run.
`storefront-monitor` already uses hosted runners (~2 min × 96/day ≈ 3.2 h/day)
and is unchanged.

### Secret: `RUNNER_STATUS_TOKEN`

Listing self-hosted runners usually needs more than the default `GITHUB_TOKEN`.
Add a repository secret:

| Name | Value |
|---|---|
| `RUNNER_STATUS_TOKEN` | Classic PAT with **`repo`** scope, **or** fine-grained PAT with this repo’s **Administration: Read** (and **Actions: Read**). |

The picker uses `RUNNER_STATUS_TOKEN` when set; otherwise it tries
`github.token`. If the API returns non-200, it **defaults to `ubuntu-latest`**
(fail-open for alerts) and prints a workflow warning.

Create under **Settings → Secrets and variables → Actions → New repository
secret**.

## box-runner

- Install dir: `/home/box/actions-runner-x402`
- No systemd on the box; kept alive by `supervise.sh` (restart loop),
  launched detached via `./start-detached.sh` (idempotent). Stop: `./stop.sh`.
- Logs: `runner.log`, `supervisor.log`, `_diag/`

## Reverting

Once billing is fixed, you can switch back to always-hosted runs by removing
`pick-runner` jobs and setting `runs-on: ubuntu-latest`, or leave the picker in
place — it will still prefer self-hosted while any runner is online.