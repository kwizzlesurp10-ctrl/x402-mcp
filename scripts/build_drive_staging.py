"""Generate Drive staging directory from git ls-files — never hand-built."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path(
    os.environ.get("GOAL_SCRATCH", str(Path(tempfile.gettempdir()) / "x402-mcp-evidence"))
)
STAGING = SCRATCH / "x402-drive-staging"

TOP_DIRS = ("code", "tests", "docs", "manifests", "deployment", "screenshots", "scripts")
CODE_ROOT = {
    ".env.example",
    ".gitignore",
    "CHANGES.md",
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "run_stdio.py",
}

REQUIRED_PROOF_PATHS = (
    "code/app/main.py",
    "deployment/Dockerfile",
    "scripts/run_goal_verification.ps1",
    "scripts/verify_docker.py",
    "scripts/build_drive_staging.py",
    "scripts/capture_goal_evidence.py",
)


def map_path(git_path: str) -> str | None:
    if git_path.startswith("app/"):
        return f"code/{git_path}"
    if git_path in CODE_ROOT:
        return f"code/{git_path}"
    for top in TOP_DIRS:
        if top == "code":
            continue
        if git_path.startswith(f"{top}/"):
            return git_path
    if git_path.startswith("scripts/"):
        return git_path
    return None


def git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def build_staging() -> list[str]:
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir(parents=True, exist_ok=True)

    manifest_lines: list[str] = []
    for git_path in sorted(git_ls_files()):
        rel = map_path(git_path)
        if rel is None:
            continue
        dest = STAGING / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / git_path, dest)
        manifest_lines.append(rel)

    manifest_path = SCRATCH / "drive_staging_manifest.txt"
    header = f"=== x402-drive-staging manifest ({len(manifest_lines)} files) ===\n"
    manifest_path.write_text(header + "\n".join(manifest_lines) + "\n", encoding="utf-8")

    listing = [{"name": Path(p).name, "path": p} for p in manifest_lines]
    (SCRATCH / "drive_staging_listing.json").write_text(
        json.dumps(listing, indent=2), encoding="utf-8"
    )

    missing = [p for p in REQUIRED_PROOF_PATHS if p not in manifest_lines]
    if missing:
        raise RuntimeError(f"staging missing required proof paths: {missing}")

    for top in TOP_DIRS:
        if not (STAGING / top).is_dir():
            raise RuntimeError(f"staging missing top-level folder: {top}/")

    return manifest_lines


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    try:
        files = build_staging()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        err = SCRATCH / "drive_staging_error.log"
        err.write_text(str(exc) + "\n", encoding="utf-8")
        print(exc, file=sys.stderr)
        return 1
    print(f"staging_ok files={len(files)} dir={STAGING}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())