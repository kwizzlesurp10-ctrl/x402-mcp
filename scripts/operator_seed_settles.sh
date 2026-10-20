#!/usr/bin/env bash
# DEPRECATED entrypoint — use scripts/city_keepalive.py (city/MN only).
# Kept so old muscle memory still works; no longer settles Pulse/tx-decision.
#
# Usage:
#   bash scripts/operator_seed_settles.sh              # dry-run plan
#   bash scripts/operator_seed_settles.sh --execute    # local buyer settles
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ENV_FILE="${BUYER_ENV:-/home/keef/secrets/x402-buyer.env}"
export BUYER_ENV="$ENV_FILE"
exec .venv/bin/python scripts/city_keepalive.py "$@"
