#!/usr/bin/env bash
# Stop x402 backend and Cloudflare quick tunnel.
set -euo pipefail
LOG_DIR="${LOG_DIR:-/tmp}"
PORT="${PORT:-8402}"

kill_pidfile() {
  local f="$1"
  if [[ -f "$f" ]]; then
    kill "$(cat "$f")" 2>/dev/null || true
    rm -f "$f"
  fi
}

echo "==> stopping backend/tunnel pidfiles"
kill_pidfile "$LOG_DIR/x402-backend.pid"
kill_pidfile "$LOG_DIR/cloudflared.pid"

# belt-and-suspenders: free the port
python3 - "$PORT" <<'PY'
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
                print(f"killed {pid}")
            except ProcessLookupError:
                pass
PY

echo "stack down"
