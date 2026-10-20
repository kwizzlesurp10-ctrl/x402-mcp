# Self-hosted runner (box-runner)

GitHub-hosted Actions minutes are locked while the account has a failed
payment, so every workflow except the (disabled) storefront monitor runs on a
repo-level self-hosted runner instead: `runs-on: [self-hosted, linux, box]`.

- Runner: `box-runner`, labels `self-hosted, linux, x64, box`
- Install dir on the box: `/home/box/actions-runner-x402`
- Kept alive by `supervise.sh` (restart loop), launched detached via
  `./start-detached.sh` (idempotent). Stop with `./stop.sh`.
- Logs: `runner.log`, `supervisor.log`, `_diag/`

To go back to GitHub-hosted runners once billing is fixed, change
`runs-on: [self-hosted, linux, box]` back to `runs-on: ubuntu-latest`.
