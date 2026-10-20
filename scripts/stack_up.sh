#!/usr/bin/env bash
# Start x402 backend (+ optional Cloudflare quick tunnel). Updates PUBLIC_BASE_URL when tunnel is used.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${X402_PYTHON:-/tmp/x402-faucet-venv/bin/python}"
CF_BIN="${CLOUDFLARED:-/tmp/cloudflared}"
PORT="${PORT:-8402}"
USE_TUNNEL="${USE_TUNNEL:-1}"
LOG_DIR="${LOG_DIR:-/tmp}"

if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

load_env() {
  set -a
  # shellcheck disable=SC1091
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      ''|\#*) continue ;;
      *=*)
        k="${line%%=*}"
        v="${line#*=}"
        v="${v%\"}"; v="${v#\"}"
        export "$k=$v"
        ;;
    esac
  done < .env
  set +a
}

kill_port() {
  local port="$1"
  if command -v ss >/dev/null; then
    python3 - "$port" <<'PY'
import os, re, signal, subprocess, sys
port = sys.argv[1]
try:
    out = subprocess.check_output(["ss", "-tlnp"], text=True, errors="replace")
except Exception:
    raise SystemExit(0)
for line in out.splitlines():
    if f":{port}" in line and "LISTEN" in line:
        for m in re.finditer(r"pid=(\d+)", line):
            pid = int(m.group(1))
            try:
                os.kill(pid, 9)
                print(f"killed pid {pid} on :{port}", flush=True)
            except ProcessLookupError:
                pass
PY
  fi
}

echo "==> stopping old listeners on :$PORT"
kill_port "$PORT"
sleep 1

load_env
export PORT

echo "==> starting backend (uvicorn)"
nohup "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" \
  >"$LOG_DIR/x402-backend.log" 2>&1 &
echo $! >"$LOG_DIR/x402-backend.pid"
sleep 2

if ! curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null; then
  echo "backend failed to start; see $LOG_DIR/x402-backend.log"
  tail -30 "$LOG_DIR/x402-backend.log" || true
  exit 1
fi
echo "backend OK pid=$(cat "$LOG_DIR/x402-backend.pid")"

PUBLIC_URL="${PUBLIC_BASE_URL:-http://127.0.0.1:${PORT}}"

if [[ "$USE_TUNNEL" == "1" ]]; then
  if [[ ! -x "$CF_BIN" ]]; then
    echo "cloudflared not found at $CF_BIN — installing to /tmp/cloudflared"
    curl -sL -o /tmp/cloudflared \
      "https://github.com/cloudflare/cloudflared/releases/download/2025.2.1/cloudflared-linux-amd64"
    chmod +x /tmp/cloudflared
    CF_BIN=/tmp/cloudflared
  fi
  # stop previous tunnel
  if [[ -f "$LOG_DIR/cloudflared.pid" ]]; then
    kill "$(cat "$LOG_DIR/cloudflared.pid")" 2>/dev/null || true
  fi
  : >"$LOG_DIR/cloudflared.log"
  nohup "$CF_BIN" tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate \
    >"$LOG_DIR/cloudflared.log" 2>&1 &
  echo $! >"$LOG_DIR/cloudflared.pid"
  echo "==> waiting for trycloudflare URL..."
  PUBLIC_URL=""
  for i in $(seq 1 30); do
    PUBLIC_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_DIR/cloudflared.log" | head -1 || true)"
    if [[ -n "$PUBLIC_URL" ]]; then
      break
    fi
    sleep 1
  done
  if [[ -z "$PUBLIC_URL" ]]; then
    echo "tunnel URL not found; backend still local-only"
    PUBLIC_URL="http://127.0.0.1:${PORT}"
  else
    echo "tunnel $PUBLIC_URL"
    # persist PUBLIC_BASE_URL for next process start / scripts
    if grep -q '^PUBLIC_BASE_URL=' .env; then
      sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=${PUBLIC_URL}|" .env
    else
      echo "PUBLIC_BASE_URL=${PUBLIC_URL}" >>.env
    fi
  fi
fi

echo ""
echo "=== stack up ==="
echo "health:  http://127.0.0.1:${PORT}/health"
echo "doctor:  http://127.0.0.1:${PORT}/doctor"
echo "ops:     http://127.0.0.1:${PORT}/ops/status"
echo "demo:    ${PUBLIC_URL}/demo/paid"
echo "info:    ${PUBLIC_URL}/demo/paid/info"
echo "bazaar:  python scripts/poll_bazaar_listing.py"
echo "logs:    $LOG_DIR/x402-backend.log  $LOG_DIR/cloudflared.log"
