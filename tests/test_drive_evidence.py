"""Drive evidence contract — remote listing must cover staged manifest paths."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

SCRATCH = Path(
    os.environ.get(
        "GOAL_SCRATCH",
        r"C:\Users\Keith\AppData\Local\Temp\grok-goal-96e31bb2e41a\implementer",
    )
)

REQUIRED_TOP = ("code", "tests", "docs", "manifests", "deployment", "screenshots", "scripts")

PROOF_PATHS = (
    "code/app/main.py",
    "deployment/Dockerfile",
    "scripts/run_goal_verification.ps1",
    "scripts/verify_docker.py",
    "scripts/build_drive_staging.py",
    "scripts/capture_goal_evidence.py",
    "scripts/drive/upload-x402-folders.ts",
)


def test_vendored_drive_upload_script_in_repo() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "drive" / "upload-x402-folders.ts"
    assert script.exists(), "Drive upload script must live in project scripts/drive/"


def _load_manifest_lines() -> list[str]:
    path = SCRATCH / "drive_staging_manifest.txt"
    if not path.exists():
        pytest.skip("missing drive_staging_manifest.txt — run capture_goal_evidence first")
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("===")
    ]
    return lines


def _load_remote_entries() -> list[dict]:
    path = SCRATCH / "drive_remote_listing.json"
    if not path.exists():
        pytest.skip("missing drive_remote_listing.json — run capture_goal_evidence first")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("method") == "in_folder_listing_same_session"
    return data.get("entries", [])


def _remote_paths(entries: list[dict]) -> set[str]:
    paths: set[str] = set()
    for entry in entries:
        p = entry.get("path", "")
        name = entry.get("name", "")
        paths.add(p)
        if p:
            paths.add(p.split("/")[-1])
        if name:
            paths.add(name)
    return paths


def test_no_stale_failed_collect_artifacts() -> None:
    """Reject cherry-picked evidence: stale collect*.json must be removed after capture."""
    stale = sorted(SCRATCH.glob("drive_remote_listing_collect*.json"))
    assert not stale, f"remove stale collect artifacts: {[p.name for p in stale]}"


def test_remote_listing_ok_flag() -> None:
    path = SCRATCH / "drive_remote_listing.json"
    if not path.exists():
        pytest.skip("missing drive_remote_listing.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("ok") is True, f"remote listing not ok: {data.get('missingFromRemote')}"
    assert data.get("method") == "in_folder_listing_same_session"


def test_all_manifest_paths_present_remotely() -> None:
    manifest = _load_manifest_lines()
    entries = _load_remote_entries()
    remote = _remote_paths(entries)
    missing = [
        line
        for line in manifest
        if not (
            line in remote
            or line.split("/")[-1] in remote
            or any(e.get("path") == line or e.get("path", "").endswith(line.split("/")[-1]) for e in entries)
        )
    ]
    assert not missing, f"remote missing manifest paths: {missing[:10]}"


@pytest.mark.parametrize("top", REQUIRED_TOP)
def test_remote_has_top_level_folder(top: str) -> None:
    entries = _load_remote_entries()
    found = any(
        e.get("path") == top
        or e.get("path", "").startswith(f"{top}/")
        or e.get("name") == top
        for e in entries
    )
    assert found, f"remote listing missing top folder: {top}/"


@pytest.mark.parametrize("proof_path", PROOF_PATHS)
def test_remote_has_proof_path(proof_path: str) -> None:
    entries = _load_remote_entries()
    file_name = proof_path.split("/")[-1]
    found = any(
        e.get("path") == proof_path
        or e.get("path", "").endswith(file_name)
        or e.get("name") == file_name
        for e in entries
    )
    assert found, f"remote listing missing proof path: {proof_path}"