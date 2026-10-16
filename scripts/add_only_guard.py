"""Classify a git name-status diff as add-only vs mutation of existing files.

Existing tracked files must not be modified, deleted, renamed, copied, or
type-changed without the operator clicking Approve on GitHub Environment
`operator-approve`. New files (status A) are allowed.

This script never honours OPERATOR_APPROVED / AGENT_APPROVED env vars — agents
can set those. The only bypass is the Environment click in CI.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass

# git --name-status letters that mean "this path already existed".
MUTATION_STATUSES = frozenset({"M", "D", "R", "C", "T"})
ADD_STATUSES = frozenset({"A"})


@dataclass(frozen=True)
class DiffEntry:
    status: str
    path: str
    orig_path: str | None = None


def _status_letter(token: str) -> str:
    """'R100' / 'C075' / 'M' -> the leading status letter."""
    token = (token or "").strip()
    return token[:1].upper() if token else ""


def parse_name_status(text: str) -> list[DiffEntry]:
    """Parse `git diff --name-status` output into entries."""
    entries: list[DiffEntry] = []
    for raw in (text or "").splitlines():
        line = raw.strip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        status = _status_letter(parts[0])
        if status in {"R", "C"} and len(parts) >= 3:
            entries.append(DiffEntry(status=status, path=parts[2], orig_path=parts[1]))
        elif len(parts) >= 2:
            entries.append(DiffEntry(status=status, path=parts[1]))
    return entries


def classify(entries: list[DiffEntry]) -> tuple[list[DiffEntry], list[DiffEntry]]:
    """Split entries into (adds, mutations). Unknown status letters are mutations."""
    adds: list[DiffEntry] = []
    mutations: list[DiffEntry] = []
    for entry in entries:
        if entry.status in ADD_STATUSES:
            adds.append(entry)
        else:
            mutations.append(entry)
    return adds, mutations


def is_add_only(
    entries: list[DiffEntry], extra_env: dict[str, str] | None = None
) -> bool:
    """True only when every entry is a new file. Env vars never bypass."""
    _ = extra_env  # agents can export this; it is intentionally ignored
    _, mutations = classify(entries)
    return not mutations


def mutation_report(entries: list[DiffEntry]) -> str:
    _, mutations = classify(entries)
    if not mutations:
        return ""
    lines = ["existing files mutated (add-only policy):"]
    for entry in mutations:
        if entry.orig_path:
            lines.append(f"  {entry.status} {entry.orig_path} -> {entry.path}")
        else:
            lines.append(f"  {entry.status} {entry.path}")
    return "\n".join(lines)


def summarize(entries: list[DiffEntry]) -> str:
    adds, mutations = classify(entries)
    payload = {
        "mutation": bool(mutations),
        "adds": [e.path for e in adds],
        "mutations": [
            {"status": e.status, "path": e.path, **({"orig_path": e.orig_path} if e.orig_path else {})}
            for e in mutations
        ],
    }
    return json.dumps(payload)


def diff_args(base: str | None = None, rev_range: str | None = None) -> list[str]:
    """Build the git diff argv. `--range` wins so CI can pin BEFORE...SHA."""
    if rev_range:
        spec = rev_range
    else:
        spec = f"{base or 'origin/master'}...HEAD"
    return ["git", "diff", "--name-status", "--find-renames", spec]


def git_name_status(base: str | None = None, rev_range: str | None = None) -> str:
    """`git diff --name-status --find-renames` against base...HEAD or an explicit range."""
    cmd = diff_args(base=base, rev_range=rev_range)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git diff failed: {' '.join(cmd)}")
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="origin/master",
        help="Git ref to diff against (triple-dot merge-base). Default: origin/master",
    )
    parser.add_argument(
        "--range",
        dest="rev_range",
        default=None,
        help="Explicit git rev range (e.g. BEFORE...SHA). Overrides --base.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print {mutation, adds, mutations} JSON on stdout",
    )
    parser.add_argument(
        "--exit-zero",
        action="store_true",
        help="Always exit 0 (CI classify job reads JSON instead of the status code)",
    )
    args = parser.parse_args(argv)
    entries = parse_name_status(
        git_name_status(base=args.base, rev_range=args.rev_range)
    )
    report = mutation_report(entries)
    if args.as_json:
        print(summarize(entries))
    elif report:
        print(report, file=sys.stderr)
    else:
        print("add-only: ok")
    if args.exit_zero:
        return 0
    return 1 if report else 0


if __name__ == "__main__":
    raise SystemExit(main())
