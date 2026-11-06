#!/usr/bin/env bash
# Run benchmark harness twice: baseline git ref vs HEAD, same deps on this machine.
# Does not merge, deploy, or spend.
#
# Usage:
#   ./scripts/compare_a2a_benchmark_refs.sh e6c542a64ea2738bedeca941063a20ae2f3d6e31 HEAD
#
# Outputs under /opt/cursor/artifacts/:
#   a2a_bench_<baseline>.json, a2a_bench_<head>.json, A2A_BENCHMARK_COMPARISON.md
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
BASE_REF="${1:?baseline ref}"
HEAD_REF="${2:-HEAD}"
ARTIFACTS="${ARTIFACTS_DIR:-/opt/cursor/artifacts}"
mkdir -p "$ARTIFACTS"

export X402_PAY_TO_ADDRESS="${X402_PAY_TO_ADDRESS:-0x0d25A44f74868eCE53B305C97139CF4B62963410}"
export REDIS_URL="${REDIS_URL:-redis://benchmark-fake}"
export PYTHONPATH="$ROOT"
# Stable knobs unless operator overrides
export BENCH_WARMUP="${BENCH_WARMUP:-15}"
export BENCH_SAMPLES="${BENCH_SAMPLES:-120}"
export BENCH_CONCURRENCY="${BENCH_CONCURRENCY:-8}"

START_REF="$(git rev-parse HEAD)"
# Use the harness **from the PR head** on both checkouts so scenarios stay identical.
TMP_BENCH="$(mktemp)"
trap 'rm -f "$TMP_BENCH"' EXIT
git show "${HEAD_REF}:scripts/benchmark_x402_latency.py" >"$TMP_BENCH"

run_at_ref() {
  local ref="$1"
  local out="$2"
  git checkout -q "$ref"
  python3 "$TMP_BENCH" --json-out "$out"
}

B_BASE="$(git rev-parse --short "$BASE_REF" 2>/dev/null || echo "$BASE_REF")"
B_HEAD="$(git rev-parse --short "$HEAD_REF" 2>/dev/null || echo "$HEAD_REF")"

BASE_JSON="$ARTIFACTS/a2a_bench_${B_BASE}.json"
HEAD_JSON="$ARTIFACTS/a2a_bench_${B_HEAD}.json"

run_at_ref "$BASE_REF" "$BASE_JSON"
run_at_ref "$HEAD_REF" "$HEAD_JSON"
git checkout -q "$START_REF"

export BASE_JSON HEAD_JSON ARTIFACTS
python - <<'PY'
import json, os, sys
from pathlib import Path
base_p = Path(os.environ["BASE_JSON"])
head_p = Path(os.environ["HEAD_JSON"])
art = Path(os.environ.get("ARTIFACTS", "/opt/cursor/artifacts"))
base = json.loads(base_p.read_text())
head = json.loads(head_p.read_text())
lines = [
    "# A2A benchmark comparison",
    "",
    f"- Baseline file: `{base_p}`",
    f"- Head file: `{head_p}`",
    f"- Baseline commit: `{base.get('git_commit')}`",
    f"- Head commit: `{head.get('git_commit')}`",
    "",
    "## Per-scenario (head vs baseline)",
    "",
    "| Scenario | Metric | Baseline | Head |",
    "|----------|--------|----------|------|",
]
by_name = {r["name"]: r for r in head.get("results", []) if isinstance(r, dict) and "name" in r}
for r0 in base.get("results", []):
    if not isinstance(r0, dict) or "name" not in r0:
        continue
    name = r0["name"]
    r1 = by_name.get(name)
    if not r1:
        continue
    for k in ("p50_ms", "p95_ms", "p99_ms", "throughput_per_s", "n", "errors"):
        if k in r0 or k in r1:
            lines.append(f"| {name} | {k} | {r0.get(k)} | {r1.get(k)} |")
lines += [
    "",
    "## Limitations",
    "",
    "- Mock facilitator only; no chain spend.",
    "- fakeredis is not Redis server semantics under multi-worker TCP.",
    "- Paid-path samples capped by `BENCH_PAID_SAMPLES` (default 40).",
    "",
]
out_md = art / "A2A_BENCHMARK_COMPARISON.md"
out_md.write_text("\n".join(lines), encoding="utf-8")
print(str(out_md))
PY
