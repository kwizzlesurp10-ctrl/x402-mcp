"""Docker launch verification — build, run twice, probe /health and manifest."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path(
    os.environ.get(
        "GOAL_SCRATCH",
        r"C:\Users\Keith\AppData\Local\Temp\grok-goal-96e31bb2e41a\implementer",
    )
)
IMAGE = "x402-mcp"
PORT = 8402
EXPECTED_TOOLS = 10
SERVICE_ID = "x402-micropayments-mcp"


def run(cmd: list[str], *, cwd: Path = ROOT, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def probe_boot(log_lines: list[str], boot: int) -> bool:
    import httpx

    container_name = f"x402-mcp-verify-{boot}"
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True)
    proc = subprocess.Popen(
        [
            "docker",
            "run",
            "--name",
            container_name,
            "-p",
            f"{PORT}:{PORT}",
            IMAGE,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    ok = False
    try:
        time.sleep(5)
        health = httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=15)
        manifest = httpx.get(f"http://127.0.0.1:{PORT}/.well-known/mcp", timeout=15)
        manifest_json = manifest.json()
        tool_count = len(manifest_json.get("tools", []))
        log_lines.append(f"=== boot {boot} ===")
        log_lines.append(f"health_status={health.status_code}")
        log_lines.append(f"health_body={health.text}")
        log_lines.append(f"manifest_status={manifest.status_code}")
        log_lines.append(f"manifest_tool_count={tool_count}")
        log_lines.append(f"manifest_body={manifest.text}")
        ok = (
            health.status_code == 200
            and SERVICE_ID in health.text
            and manifest.status_code == 200
            and tool_count == EXPECTED_TOOLS
        )
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True)
        proc.kill()
    return ok


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    log_path = SCRATCH / "docker_launch.log"
    lines: list[str] = ["=== Docker verification ===", f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}"]

    info = run(["docker", "info"])
    if info.returncode != 0:
        lines.append("docker info FAILED")
        lines.append(info.stderr or info.stdout)
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1
    lines.append("docker info OK")

    build = run(["docker", "build", "-f", "deployment/Dockerfile", "-t", IMAGE, "."])
    lines.append(f"docker build exit={build.returncode}")
    if build.returncode != 0:
        lines.append(build.stdout[-2000:] if build.stdout else "")
        lines.append(build.stderr[-2000:] if build.stderr else "")
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    boots_ok = all(probe_boot(lines, boot) for boot in (1, 2))
    lines.append(f"both_boots_ok={boots_ok}")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if boots_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())