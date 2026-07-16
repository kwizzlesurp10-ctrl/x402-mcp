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
EXPECTED_TOOLS = 15
SERVICE_ID = "x402-micropayments-mcp"


def run(cmd: list[str], *, cwd: Path = ROOT, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def capture_docker_info() -> tuple[bool, str]:
    info = run(["docker", "info"])
    info_text = (info.stdout or "") + (info.stderr or "")
    (SCRATCH / "docker_info.log").write_text(info_text, encoding="utf-8")
    return info.returncode == 0 and "Server Version" in info_text, info_text


def capture_docker_images(label: str) -> str:
    images = run(["docker", "images", IMAGE, "--format", "{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}"])
    text = (images.stdout or "").strip()
    log_path = SCRATCH / "docker_images.log"
    block = f"=== {label} ===\n{time.strftime('%Y-%m-%d %H:%M:%S')}\n{text or '(no image)'}\n"
    if log_path.exists():
        log_path.write_text(log_path.read_text(encoding="utf-8") + "\n" + block, encoding="utf-8")
    else:
        log_path.write_text(block, encoding="utf-8")
    return text


def write_daemon_unavailable(reason: str) -> int:
    log_path = SCRATCH / "docker_launch.log"
    log_path.write_text(
        "\n".join(
            [
                "=== Docker verification ===",
                f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                "status: DAEMON_UNAVAILABLE",
                f"reason: {reason}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return 1


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
    health_path = SCRATCH / f"health_boot{boot}.json"
    manifest_path = SCRATCH / f"manifest_boot{boot}.json"
    try:
        time.sleep(5)
        health = httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=15)
        manifest = httpx.get(f"http://127.0.0.1:{PORT}/.well-known/mcp", timeout=15)
        manifest_json = manifest.json()
        tool_count = len(manifest_json.get("tools", []))

        health_path.write_text(health.text, encoding="utf-8")
        manifest_path.write_text(manifest.text, encoding="utf-8")

        log_lines.append(f"=== boot {boot} ===")
        log_lines.append(f"health_status={health.status_code}")
        log_lines.append(f"health_json={health_path}")
        log_lines.append(f"manifest_status={manifest.status_code}")
        log_lines.append(f"manifest_tool_count={tool_count}")
        log_lines.append(f"manifest_json={manifest_path}")
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

    info_ok, info_text = capture_docker_info()
    if not info_ok:
        return write_daemon_unavailable("docker info failed or missing Server Version block")

    lines.append("docker info OK")
    lines.append(f"docker_info_log={SCRATCH / 'docker_info.log'}")

    pre_build_images = capture_docker_images("pre_build")
    lines.append(f"docker_images_pre_build={pre_build_images or '(none)'}")

    build = run(["docker", "build", "-f", "deployment/Dockerfile", "-t", IMAGE, "."])
    lines.append(f"docker build exit={build.returncode}")
    if build.returncode != 0:
        lines.append((build.stdout or "")[-2000:])
        lines.append((build.stderr or "")[-2000:])
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    post_build_images = capture_docker_images("post_build")
    lines.append(f"docker_images_post_build={post_build_images}")
    lines.append(f"docker_images_log={SCRATCH / 'docker_images.log'}")
    if IMAGE not in post_build_images:
        lines.append(f"image_tag_missing={IMAGE}")
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    boots_ok = all(probe_boot(lines, boot) for boot in (1, 2))
    lines.append(f"both_boots_ok={boots_ok}")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if boots_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())