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
UPLOAD_SCRIPT = ROOT / "scripts" / "drive" / "upload-x402-folders.ts"
PARENT_ROOT = Path(r"C:\Users\Keith")

sys.path.insert(0, str(ROOT))
from app.tools_registry import EXPECTED_TOOL_NAMES  # noqa: E402

EXPECTED_TOOLS = sorted(EXPECTED_TOOL_NAMES)

REQUIRED_PROOF_PATHS = {
    "code/app/main.py",
    "deployment/Dockerfile",
    "scripts/run_goal_verification.ps1",
    "scripts/verify_docker.py",
    "scripts/build_drive_staging.py",
    "scripts/capture_goal_evidence.py",
    "scripts/drive/upload-x402-folders.ts",
}


def _resolve_npx() -> str:
    if sys.platform == "win32":
        for candidate in (
            r"C:\Program Files\nodejs\npx.cmd",
            r"C:\Users\Keith\AppData\Roaming\npm\npx.cmd",
        ):
            if Path(candidate).exists():
                return candidate
    return "npx"


def run_cmd(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, **(env or {}), "GOAL_SCRATCH": str(SCRATCH)}
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=merged, shell=False)


def _initial_commit_sha() -> str:
    proc = run_cmd(["git", "-C", str(ROOT), "rev-list", "--max-parents=0", "HEAD"])
    sha = proc.stdout.strip()
    if not sha:
        raise RuntimeError("could not resolve initial commit sha")
    return sha


def _parse_manifest_lines() -> list[str]:
    manifest_path = SCRATCH / "drive_staging_manifest.txt"
    if not manifest_path.exists():
        return []
    return [
        line.strip()
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("===")
    ]


def _remote_paths_from_listing(data: dict) -> set[str]:
    paths: set[str] = set()
    for entry in data.get("entries", []):
        p = entry.get("path", "")
        name = entry.get("name", "")
        if p:
            paths.add(p)
            paths.add(p.split("/")[-1])
        if name:
            paths.add(name)
    return paths


def step_scope_anchor() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)

    base = _initial_commit_sha()
    head_sha = run_cmd(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip()
    diff = run_cmd(["git", "-C", str(ROOT), "diff", f"{base}..HEAD"])
    stat = run_cmd(["git", "-C", str(ROOT), "diff", f"{base}..HEAD", "--stat"])
    sub_head = run_cmd(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip()
    patch_body = (
        f"# sub_repo={ROOT}\n# base_sha={base}\n# head_sha={head_sha}\n# sub_head={sub_head}\n"
        + diff.stdout
        + "\n"
        + stat.stdout
    )
    (SCRATCH / "goal_changes.patch").write_text(patch_body, encoding="utf-8")
    parent_patch = PARENT_ROOT / "x402-mcp-changes.patch"
    parent_patch.write_text(patch_body, encoding="utf-8")

    # Parent tracks gitlink + patch; sub-repo holds the real source edits.
    name_only = run_cmd(["git", "-C", str(ROOT), "diff", "--name-only", f"{base}..HEAD"])
    sub_paths = [
        f"x402-mcp/{line.strip()}"
        for line in name_only.stdout.splitlines()
        if line.strip()
    ]
    parent_changed = [
        ".gitignore",
        ".gitmodules",
        "x402-mcp",
        "x402-mcp-changes.patch",
        *sub_paths,
    ]
    (SCRATCH / "CHANGED_FILES").write_text("\n".join(parent_changed) + "\n", encoding="utf-8")
    (SCRATCH / "goal_scope_files.txt").write_text(
        "\n".join(parent_changed)
        + f"\n# sub_repo={ROOT}\n# sub_repo_head={sub_head}\n# base_sha={base}\n",
        encoding="utf-8",
    )


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
    staging_listing_path = SCRATCH / "drive_staging_listing.json"
    remote_path = SCRATCH / "drive_remote_listing.json"
    manifest_path = SCRATCH / "drive_staging_manifest.txt"
    log_path = SCRATCH / "drive_upload.log"

    if result_path.exists():
        result_path.unlink()
    if remote_path.exists():
        remote_path.unlink()

    if not UPLOAD_SCRIPT.exists():
        body = f"upload script missing: {UPLOAD_SCRIPT}\n"
        log_path.write_text("=== Drive upload SKIPPED ===\n" + body, encoding="utf-8")
        return 1

    drive_deps = DRIVE_SKILL / "node_modules"
    drive_auth = DRIVE_SKILL / "drive-auth.json"
    drive_env: dict[str, str] = {}
    if drive_deps.exists():
        drive_env["NODE_PATH"] = str(drive_deps)
    if drive_auth.exists():
        drive_env["DRIVE_AUTH_PATH"] = str(drive_auth)
    proc = run_cmd(
        [
            _resolve_npx(),
            "tsx",
            str(UPLOAD_SCRIPT),
            "--staging",
            str(staging),
            "--output",
            str(result_path),
            "--listing",
            str(staging_listing_path),
            "--remote",
            str(remote_path),
            "--manifest",
            str(manifest_path),
        ],
        cwd=DRIVE_SKILL if drive_deps.exists() else ROOT,
        env=drive_env,
    )

    # Drop stale/failed collect-only artifacts so evidence tests only see current run.
    for pattern in (
        "drive_remote_listing_collect*.json",
        "drive_upload_result_collect*.json",
        "drive_remote_listing_search*.json",
        "drive_upload_run*.log",
    ):
        for stale in SCRATCH.glob(pattern):
            stale.unlink(missing_ok=True)

    log_body = [
        "=== Drive upload + remote tree (same session) ===",
        f"upload_script={UPLOAD_SCRIPT}",
        proc.stdout,
        proc.stderr,
    ]
    if result_path.exists():
        log_body.append(result_path.read_text(encoding="utf-8"))
    if remote_path.exists():
        log_body.append(remote_path.read_text(encoding="utf-8"))
    log_path.write_text("\n".join(log_body) + "\n", encoding="utf-8")

    if proc.returncode != 0:
        return proc.returncode
    if not result_path.exists() or not remote_path.exists():
        return 1

    data = json.loads(result_path.read_text(encoding="utf-8"))
    remote = json.loads(remote_path.read_text(encoding="utf-8"))
    if not data.get("ok") or not remote.get("ok"):
        return 1

    manifest_lines = _parse_manifest_lines()
    remote_paths = _remote_paths_from_listing(remote)
    missing = [
        line
        for line in manifest_lines
        if not (
            line in remote_paths
            or line.split("/")[-1] in remote_paths
            or any(
                e.get("path") == line or e.get("path", "").endswith(line.split("/")[-1])
                for e in remote.get("entries", [])
            )
        )
    ]
    if missing:
        parity_log = SCRATCH / "drive_manifest_parity.log"
        parity_log.write_text(
            f"missing_count={len(missing)}\nmissing={missing}\n",
            encoding="utf-8",
        )
        return 1

    if not REQUIRED_PROOF_PATHS.issubset(set(remote.get("proofPathsPresent", []))):
        return 1

    return 0


def step_git() -> int:
    log = SCRATCH / "git.log"
    logon = run_cmd(["git", "-C", str(ROOT), "log", "--oneline"])
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