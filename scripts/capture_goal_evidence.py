"""Single entry point — run plan verification steps 1→5 and write all scratch evidence."""

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
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

DRIVE_SKILL = Path(r"C:\Users\Keith\.grok\skills\google-drive-playwright")
UPLOAD_SCRIPT = DRIVE_SKILL / "scripts" / "upload-x402-folders.ts"

EXPECTED_TOOLS = [
    "discover_services",
    "get_payment_requirements",
    "pay_and_fetch",
    "build_seller_requirements",
    "verify_payment_payload",
    "get_supported_networks",
    "get_pro_upgrade_requirements",
    "activate_pro_tier",
    "get_tool_credits_requirements",
    "purchase_tool_credits",
]


def run_cmd(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, **(env or {}), "GOAL_SCRATCH": str(SCRATCH)}
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=merged)


def step_scope_anchor() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    result = run_cmd(["git", "-C", str(ROOT), "ls-files"])
    (SCRATCH / "goal_scope_files.txt").write_text(result.stdout, encoding="utf-8")


def step_readme() -> int:
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    lines = [
        "=== README verification ===",
        f"features_10_tools={'10 MCP tools' in text}",
        f"features_not_6={'6 MCP tools' not in text}",
    ]
    missing = [t for t in EXPECTED_TOOLS if f"`{t}`" not in text]
    lines.append(f"missing_tools={missing}")
    lines.append(f"all_tools_present={not missing}")
    (SCRATCH / "readme_verify.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if not missing and "10 MCP tools" in text else 1


def step_drive_staging() -> int:
    proc = run_cmd([str(PYTHON), "scripts/build_drive_staging.py"])
    if proc.returncode != 0:
        log = SCRATCH / "drive_upload.log"
        log.write_text(
            "=== Drive staging FAILED ===\n" + proc.stdout + proc.stderr + "\n",
            encoding="utf-8",
        )
        return proc.returncode
    return 0


def step_drive_upload() -> int:
    staging = SCRATCH / "x402-drive-staging"
    result_path = SCRATCH / "drive_upload_result.json"
    listing_path = SCRATCH / "drive_folder_listing.json"
    log_path = SCRATCH / "drive_upload.log"

    if not UPLOAD_SCRIPT.exists():
        body = f"upload script missing: {UPLOAD_SCRIPT}\n"
        log_path.write_text("=== Drive upload SKIPPED ===\n" + body, encoding="utf-8")
        return 1

    proc = run_cmd(
        [
            "npx",
            "tsx",
            str(UPLOAD_SCRIPT),
            "--staging",
            str(staging),
            "--output",
            str(result_path),
            "--listing",
            str(listing_path),
        ],
        cwd=DRIVE_SKILL,
    )

    log_body = ["=== Drive upload ===", proc.stdout, proc.stderr]
    if result_path.exists():
        log_body.append(result_path.read_text(encoding="utf-8"))
    if listing_path.exists():
        listing = json.loads(listing_path.read_text(encoding="utf-8"))
        proof = [e["path"] for e in listing if e["path"] in (
            "code/app/main.py",
            "deployment/Dockerfile",
            "scripts/run_goal_verification.ps1",
            "scripts/verify_docker.py",
            "scripts/build_drive_staging.py",
            "scripts/capture_goal_evidence.py",
        )]
        log_body.append(f"proof_paths_present={proof}")
    log_path.write_text("\n".join(log_body) + "\n", encoding="utf-8")

    if proc.returncode != 0:
        return proc.returncode
    if result_path.exists():
        data = json.loads(result_path.read_text(encoding="utf-8"))
        if not data.get("ok"):
            return 1
    if not listing_path.exists():
        return 1
    return 0


def step_git() -> int:
    log = SCRATCH / "git.log"
    logon = run_cmd(["git", "-C", str(ROOT), "log", "--oneline", "-5"])
    status = run_cmd(["git", "-C", str(ROOT), "status", "--short"])
    body = logon.stdout + "\n=== status ===\n" + (status.stdout or "(clean working tree)\n")
    log.write_text(body, encoding="utf-8")
    has_commit = bool(logon.stdout.strip())
    clean = not status.stdout.strip()
    return 0 if has_commit and clean else 1


def ensure_docker_ready() -> bool:
    for _ in range(45):
        info = run_cmd(["docker", "info"])
        if "Server Version" in (info.stdout or info.stderr or ""):
            (SCRATCH / "docker_info.log").write_text(info.stdout or info.stderr, encoding="utf-8")
            return True
        time.sleep(4)
    info = run_cmd(["docker", "info"])
    (SCRATCH / "docker_info.log").write_text(
        (info.stdout or "") + (info.stderr or ""), encoding="utf-8"
    )
    return False


def step_docker() -> int:
    if sys.platform == "win32":
        subprocess.run(
            ["docker", "desktop", "start"],
            capture_output=True,
            text=True,
        )
        desktop = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
        if desktop.exists():
            subprocess.Popen([str(desktop)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not ensure_docker_ready():
        (SCRATCH / "docker_launch.log").write_text(
            "=== Docker verification ===\nstatus: DAEMON_UNAVAILABLE\n",
            encoding="utf-8",
        )
        return 1

    proc = run_cmd([str(PYTHON), "scripts/verify_docker.py"])
    return proc.returncode


def step_pytest() -> int:
    proc = run_cmd([str(PYTHON), "-m", "pytest", "-v"])
    (SCRATCH / "pytest.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    return proc.returncode


def write_summary(results: dict[str, int]) -> None:
    lines = ["=== Goal evidence capture summary ===", f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    for step, code in results.items():
        lines.append(f"{step}={code}")
    lines.append(f"overall={'PASS' if all(c == 0 for c in results.values()) else 'FAIL'}")
    lines.append(f"scratch={SCRATCH}")
    lines.append("entry_point=scripts/capture_goal_evidence.py")
    (SCRATCH / "verify_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    os.environ["GOAL_SCRATCH"] = str(SCRATCH)

    results: dict[str, int] = {}
    steps = [
        ("scope_anchor", step_scope_anchor),
        ("readme", step_readme),
        ("drive_staging", step_drive_staging),
        ("drive_upload", step_drive_upload),
        ("git", step_git),
        ("docker", step_docker),
        ("pytest", step_pytest),
    ]

    exit_code = 0
    for name, fn in steps:
        if name == "scope_anchor":
            fn()
            results[name] = 0
            continue
        code = fn()
        results[name] = code
        if code != 0:
            exit_code = code
            break

    write_summary(results)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())