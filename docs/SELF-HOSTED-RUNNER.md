# Self-hosted runners

GitHub-hosted Actions minutes are locked while the account has a failed
payment, so every workflow except the (disabled) storefront monitor runs on
repo-level self-hosted runners: `runs-on: [self-hosted, linux, x64]`.
Whichever matching runner is online picks up the job.

| Runner | Labels | Role |
|---|---|---|
| Keith's home PC | `self-hosted, linux, x64, keef-pc` | primary |
| `box-runner` | `self-hosted, linux, x64, box` | backup |

Jobs must stay portable across both machines: get toolchains from
`actions/setup-python`, `pnpm/action-setup`, etc., never from machine-specific
paths. `gh`, `git`, `curl`, `jq`, `python3` and `node`/`npx` must be on the
runner's PATH (sale/task/thread watch and add-only use them directly).

Note: `actions/setup-python` only ships Ubuntu builds. On non-Ubuntu hosts
(the box is Debian 13) pre-seed the runner tool cache once, e.g.
`uv python install 3.12` and copy it to
`<runner>/_work/_tool/Python/<ver>/x64` + touch `x64.complete`.

## box-runner

- Install dir: `/home/box/actions-runner-x402`
- No systemd on the box; kept alive by `supervise.sh` (restart loop),
  launched detached via `./start-detached.sh` (idempotent). Stop: `./stop.sh`.
- Logs: `runner.log`, `supervisor.log`, `_diag/`

## Reverting

Once billing is fixed, change `runs-on: [self-hosted, linux, x64]` back to
`runs-on: ubuntu-latest`.
