#!/usr/bin/env bash
# Set ONLY seller-safe secrets on the public Fly storefront from a local .env.
#
# SAFETY: the public box is seller-only (docs/DEPLOY-PLAN.md non-negotiable #1).
# This script forwards an explicit ALLOW-list and HARD-REFUSES if a spend key
# (EVM_PRIVATE_KEY / SVM_PRIVATE_KEY) ever slips into the payload. Values are
# never echoed. Run AFTER `fly auth login` and after Upstash gives a REDIS_URL.
#
# Usage:
#   REDIS_URL='rediss://...' PUBLIC_BASE_URL='https://x402-storefront.fly.dev' \
#     bash deployment/set_fly_secrets.sh [path/to/.env]
set -euo pipefail

ENV_FILE="${1:-.env}"
APP="${FLY_APP:-x402-storefront}"
ALLOW="X402_PAY_TO_ADDRESS CDP_API_KEY_ID CDP_API_KEY_SECRET"
DENY="EVM_PRIVATE_KEY SVM_PRIVATE_KEY"

[ -f "$ENV_FILE" ] || { echo "env file not found: $ENV_FILE" >&2; exit 1; }

args=()
for key in $ALLOW; do
  line="$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | head -1 || true)"
  val="${line#*=}"
  if [ -z "$val" ]; then
    echo "ERROR: $key missing/empty in $ENV_FILE" >&2
    exit 1
  fi
  args+=("${key}=${val}")
done

# Extra seller knobs not sourced from .env.
args+=("PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-https://x402-storefront.fly.dev}")
args+=("REVENUE_NETWORK=eip155:8453")
args+=("CDP_NETWORKS=eip155:8453")
args+=("DASHBOARD_ACTIONS=true")   # flip to false after the first publish
if [ -n "${REDIS_URL:-}" ]; then
  args+=("REDIS_URL=${REDIS_URL}")
else
  echo "WARNING: REDIS_URL not provided — /doctor will flag memory-mode quota." >&2
fi

# Hard guard: refuse to forward any spend key, no matter what.
for a in "${args[@]}"; do
  name="${a%%=*}"
  for bad in $DENY; do
    if [ "$name" = "$bad" ]; then
      echo "REFUSING: $bad must never reach the public seller box." >&2
      exit 2
    fi
  done
done

echo "Setting ${#args[@]} seller-safe secrets on app '$APP' (values hidden):"
for a in "${args[@]}"; do echo "  - ${a%%=*}"; done
fly secrets set --app "$APP" "${args[@]}"
echo "Done. Verify post-deploy: /health wallet_configured=false, /doctor revenue_network=eip155:8453."
