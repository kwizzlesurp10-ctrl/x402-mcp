#!/usr/bin/env python3
"""Close change-control issues whose mutation has already landed and was approved.

WHY THIS EXISTS
---------------
The `add-only` workflow opens a `change-control` issue every time it classifies
a mutation, and nothing ever closed one. Every approved pull request therefore
left TWO permanent open issues behind:

  1. `change-control: existing files mutated on pr-NNN`   (the pull_request event)
  2. `change-control: existing files mutated on push-master-<sha>`  (the push event
     that fires when the PR merges to master)

Both were verified landed and approved. All 59 sat open and 0 were ever closed,
so the queue told the operator nothing about what still needed a decision.

THE CLOSE RULE (both conditions, and both must hold)
---------------------------------------------------
  1. The mutation is ON master. For a `pr-N` issue that means the PR is merged
     or closed; for a `push-master-<sha>` issue that means the sha is an
     ancestor of master.
  2. The `change-control` check for that sha concluded SUCCESS. This is the
     approval. If a mutation landed on master WITHOUT the check going green,
     the issue is NOT closed and is reported as UNAPPROVED instead -- that is
     the case worth a human's eyes, so it stays open.

Closing is therefore only ever the removal of a question that has been answered
and acted on. An unapproved mutation is never closed by this script.

Usage:
    GITHUB_TOKEN=... python3 scripts/close_change_control_issues.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

REPO = os.environ.get("CC_REPO", "kwizzlesurp10-ctrl/x402-mcp")
LABEL = "change-control"
DEFAULT_BRANCH = os.environ.get("CC_BRANCH", "master")

# The check whose green result IS the operator's approval.
APPROVAL_CHECK = "change-control"

_PR_TITLE = re.compile(r"on pr-(\d+)\b")
_PUSH_TITLE = re.compile(r"on push-master-([0-9a-f]{7,40})\b")
_SHA_BODY = re.compile(r"- sha: `([0-9a-f]{40})`")
_RUN_BODY = re.compile(r"- workflow: \S+/actions/runs/(\d+)")

# Caches so a sweep of ~60 issues does not re-fetch the same PR list or the
# same check-runs page for every issue.
_MERGE_COMMIT_CACHE: dict[str, dict] = {}
_PRS_CACHE: list[dict] | None = None


def _run(args: list[str]) -> str | None:
    """Run gh and return stdout, or None if the call failed."""
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  gh {' '.join(args[:3])} -> {r.stderr.strip()[:160]}")
        return None
    return r.stdout


def _api(path: str) -> dict | list | None:
    out = _run(["api", path])
    if out is None:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def open_issues() -> list[dict]:
    out = _run([
        "api",
        f"repos/{REPO}/issues?labels={LABEL}&state=open&per_page=100",
    ])
    if not out:
        return []
    try:
        rows = json.loads(out)
    except json.JSONDecodeError:
        return []
    return [r for r in rows if "pull_request" not in r]


def _check_runs_for(sha: str) -> list[dict]:
    """Every check run for a sha, paging through all of them."""
    out: list[dict] = []
    page = 1
    while page <= 5:
        data = _api(
            f"repos/{REPO}/commits/{sha}/check-runs?per_page=100&page={page}"
        )
        if not isinstance(data, dict):
            break
        runs = data.get("check_runs", [])
        if not runs:
            break
        out.extend(runs)
        if len(runs) < 100:
            break
        page += 1
    return out


def _add_only_runs_for(sha: str) -> list[dict]:
    """The add-only workflow runs for a sha.

    Filter by workflow id, not by listing every run. A push to master fires
    the scheduled `watch` workflows dozens of times, so an unfiltered
    `actions/runs?head_sha=` listing is dominated by them and the one
    add-only run can fall off the end of the page.
    """
    runs = _api(f"repos/{REPO}/actions/workflows/add-only.yml/runs?head_sha={sha}&per_page=100")
    if not isinstance(runs, dict):
        return []
    return runs.get("workflow_runs", [])


def _tree_sha(sha: str) -> str | None:
    """The tree object sha for a commit -- identity of its content."""
    data = _api(f"repos/{REPO}/commits/{sha}")
    if not isinstance(data, dict):
        return None
    commit = data.get("commit") or {}
    tree = (commit.get("tree") or {}).get("sha")
    return tree


def _pr_approved_with_same_content(sha: str) -> dict | None:
    """If sha is a PR merge commit whose TREE equals a PR head that was approved.

    Why this exists. When a PR merges, master gets a squash/merge commit whose
    TREE is identical to the PR head's tree -- same bytes, different commit.
    The push-to-master add-only run then re-classifies that whole diff as a
    fresh mutation and opens a SECOND environment deployment, which nobody
    clicks because the change was already approved at PR level. That second
    deployment times out and the push run's change-control goes red, even
    though the operator approved the identical content minutes earlier via
    the PR run.

    So a red push-run whose content is byte-identical to an approved PR head
    is a duplicate notification, not an unapproved mutation. The check that
    matters is the tree, not the commit.
    """
    pr = pr_for_merge_commit(sha)
    if not pr:
        return None
    head_sha = pr["head_sha"]
    merge_tree = _tree_sha(sha)
    head_tree = _tree_sha(head_sha)
    if not merge_tree or not head_tree or merge_tree != head_tree:
        return None
    green = approval_green(head_sha)
    if green is None or not green:
        return None
    return pr


def _run_job_conclusion(run_id: int | str, job_name: str) -> str | None:
    """Conclusion of a named job inside one specific workflow run."""
    jobs = _api(f"repos/{REPO}/actions/runs/{run_id}/jobs")
    if not isinstance(jobs, dict):
        return None
    for job in jobs.get("jobs", []):
        if (job.get("name") or "") == job_name:
            return job.get("conclusion")
    return None


def _workflow_job_conclusion(sha: str, job_name: str) -> str | None:
    """Conclusion of a job in the add-only workflow for a sha, via the runs API.

    The check-runs API is NOT authoritative for these jobs. A push to master
    fires the scheduled `watch` workflows dozens of times, so the check-run
    list for a sha is enormous and the add-only job's own check run is easily
    absent from it -- PR 528/539/540 all read as "no change-control check"
    there even though the workflow run itself concluded change-control=success.

    The workflow-runs API is the source of truth: list the add-only runs for
    the sha, then read that run's jobs.
    """
    for run in _add_only_runs_for(sha):
        jobs = _api(f"repos/{REPO}/actions/runs/{run['id']}/jobs")
        if not isinstance(jobs, dict):
            continue
        for job in jobs.get("jobs", []):
            if (job.get("name") or "") == job_name:
                return job.get("conclusion")
    return None


def approval_green(sha: str) -> bool | None:
    """True/False if the change-control check was green for sha, None if unknown.

    Two sources, in order of trust:
      1. the add-only workflow run's own `change-control` job (authoritative),
      2. the commit's check-runs (fallback, and paginated -- a push to master
         fires enough scheduled workflows to push `change-control` off page 1).
    """
    conclusion = _workflow_job_conclusion(sha, APPROVAL_CHECK)
    if conclusion is not None:
        return conclusion == "success"
    for run in _check_runs_for(sha):
        if (run.get("name") or "") == APPROVAL_CHECK:
            return (run.get("conclusion") or "") == "success"
    return None


def sha_on_master(sha: str, branch: str = DEFAULT_BRANCH) -> bool | None:
    """True if sha is an ancestor of branch, using the compare API.

    NOTE the direction. We ask for compare/<sha>...<branch>, so `sha` is the
    BASE and `branch` is the HEAD. GitHub's `status` describes the HEAD
    relative to the BASE, so:
      "ahead"     -> branch has commits sha does not -> sha IS an ancestor
      "identical" -> same commit
      "behind"    -> branch is BEHIND sha -> sha is NOT on branch
      "diverged"  -> neither contains the other
    Getting this backwards marks every landed sha as "not on master", which
    is the safe-looking failure that silently closes nothing.
    """
    data = _api(f"repos/{REPO}/compare/{sha}...{branch}")
    if not isinstance(data, dict):
        return None
    status = data.get("status")
    if status in ("ahead", "identical"):
        return True
    if status in ("behind", "diverged"):
        return False
    return None


def pr_for_merge_commit(sha: str) -> dict | None:
    """If sha is a PR's merge commit, return that PR's number and head sha.

    The push-to-master add-only run re-classifies the entire squash as a
    fresh mutation of master. When the push sha is a PR's merge commit, the
    change being re-flagged is the one the PR was already approved for, so we
    want the PR's own head sha rather than the merge sha.
    """
    cached = _MERGE_COMMIT_CACHE.get(sha)
    if cached is not None:
        return cached or None
    result = None
    for pr in _prs_with_merge_commits():
        if pr.get("merge_commit_sha") == sha:
            head = (pr.get("head") or {}).get("sha")
            if head:
                result = {"number": pr.get("number"), "head_sha": head}
            break
    _MERGE_COMMIT_CACHE[sha] = result or {}
    return result


def _prs_with_merge_commits() -> list[dict]:
    """All PRs, merged or not, with their merge commit and head sha."""
    global _PRS_CACHE
    if _PRS_CACHE is None:
        _PRS_CACHE = []
        page = 1
        while page <= 10:
            data = _api(
                f"repos/{REPO}/pulls?state=all&per_page=100&page={page}"
            )
            if not isinstance(data, list) or not data:
                break
            _PRS_CACHE.extend(data)
            if len(data) < 100:
                break
            page += 1
    return _PRS_CACHE


def classify(issue: dict) -> dict:
    """Work out whether one issue is closable, and why."""
    title = issue.get("title") or ""
    body = issue.get("body") or ""
    number = issue.get("number")

    m_pr = _PR_TITLE.search(title)
    m_push = _PUSH_TITLE.search(title)
    m_sha = _SHA_BODY.search(body)

    if m_pr:
        kind = "pr"
        pr_number = int(m_pr.group(1))
        pull = _api(f"repos/{REPO}/pulls/{pr_number}")
        if not isinstance(pull, dict):
            return {"number": number, "kind": kind, "verdict": "unknown",
                    "reason": f"PR {pr_number} unreadable"}
        state = pull.get("state")
        if state == "open":
            return {"number": number, "kind": kind, "verdict": "keep",
                    "reason": f"PR {pr_number} still open"}
        head_sha = (pull.get("head") or {}).get("sha")
        if not head_sha:
            return {"number": number, "kind": kind, "verdict": "unknown",
                    "reason": f"PR {pr_number} has no head sha"}
        green = approval_green(head_sha)
        if green is None:
            return {"number": number, "kind": kind, "verdict": "unknown",
                    "reason": f"no {APPROVAL_CHECK} check on {head_sha}"}
        if not green:
            return {"number": number, "kind": kind, "verdict": "unapproved",
                    "reason": f"PR {pr_number} {state} but {APPROVAL_CHECK} was not green"}
        return {"number": number, "kind": kind, "verdict": "close",
                "reason": f"PR {pr_number} {state}; {APPROVAL_CHECK} green on {head_sha[:9]}"}

    if m_push:
        kind = "push"
        sha = m_sha.group(1) if m_sha else None
        if not sha:
            return {"number": number, "kind": kind, "verdict": "unknown",
                    "reason": "no sha in issue body"}
        landed = sha_on_master(sha)
        if landed is None:
            return {"number": number, "kind": kind, "verdict": "unknown",
                    "reason": f"compare failed for {sha[:9]}"}
        if not landed:
            return {"number": number, "kind": kind, "verdict": "keep",
                    "reason": f"{sha[:9]} not on {DEFAULT_BRANCH}"}

        # The issue body names the exact workflow run that raised it. That run
        # is the one whose `change-control` job decided this event, so it is
        # the most direct evidence available -- no sha-to-run guessing.
        m_run = _RUN_BODY.search(body)
        if m_run:
            conclusion = _run_job_conclusion(m_run.group(1), APPROVAL_CHECK)
            if conclusion == "success":
                return {"number": number, "kind": kind, "verdict": "close",
                        "reason": f"{sha[:9]} on {DEFAULT_BRANCH}; run {m_run.group(1)} {APPROVAL_CHECK} green"}
            if conclusion is not None:
                # Red push-run. Before calling it unapproved, check whether the
                # content that landed is byte-identical to something already
                # approved at PR level.
                same = _pr_approved_with_same_content(sha)
                if same:
                    return {"number": number, "kind": kind, "verdict": "close",
                            "reason": (f"{sha[:9]} on {DEFAULT_BRANCH}; identical tree to "
                                       f"PR {same['number']} head {same['head_sha'][:9]}, "
                                       f"{APPROVAL_CHECK} green there (push run "
                                       f"{m_run.group(1)} was a duplicate re-notification)")}
                return {"number": number, "kind": kind, "verdict": "unapproved",
                        "reason": f"{sha[:9]} on {DEFAULT_BRANCH} but run {m_run.group(1)} {APPROVAL_CHECK} was {conclusion}"}

        # No run recorded in the body (older issues). Fall back to the PR's own
        # approval if the sha is a PR merge commit: a push-to-master that
        # re-classifies a squash is the same change the PR already approved.
        pr = pr_for_merge_commit(sha)
        if pr:
            green = approval_green(pr["head_sha"])
            if green is None:
                return {"number": number, "kind": kind, "verdict": "unknown",
                        "reason": f"no {APPROVAL_CHECK} check on PR {pr['number']} head"}
            if not green:
                return {"number": number, "kind": kind, "verdict": "unapproved",
                        "reason": (f"{sha[:9]} is PR {pr['number']}'s merge commit but "
                                   f"{APPROVAL_CHECK} was not green on its head")}
            return {"number": number, "kind": kind, "verdict": "close",
                    "reason": (f"{sha[:9]} is PR {pr['number']}'s merge commit; "
                               f"{APPROVAL_CHECK} green on {pr['head_sha'][:9]}")}

        # Not a PR merge commit and no usable run: a direct push to master
        # that predates the workflow. There is no approval to point at, so the
        # issue stays open rather than being closed on a guess.
        return {"number": number, "kind": kind, "verdict": "unknown",
                "reason": f"no add-only run for {sha[:9]} and no PR match"}

    return {"number": number, "kind": "unknown", "verdict": "keep",
            "reason": "title matched no known pattern"}


def close_issue(number: int, reason: str) -> bool:
    body = (
        "Closed automatically: this mutation has already landed on "
        f"`{DEFAULT_BRANCH}` and the `change-control` check was green for it.\n\n"
        f"{reason}\n\n"
        "Nothing was approved here. The approval happened in the workflow run; this "
        "issue was only the notification of it, and it was never closed. Script: "
        "`scripts/close_change_control_issues.py`."
    )
    out = _run([
        "api", "-X", "PATCH", f"repos/{REPO}/issues/{number}",
        "-f", "state=closed", "-f", f"body={body}",
    ])
    return out is not None


def close_for_subject(subject: str) -> bool:
    """Close the change-control issue raised for one subject, if there is one.

    The `notify` job in the add-only workflow opens an issue keyed on
    event_key("change-control", subject), where subject is "pr-NNN" for a
    pull_request and "push-<ref>-<sha12>" for a push. The change-control job
    derives the same key, so when its check passes it can find and close the
    issue it just answered -- instead of leaving a permanent record of a
    decision that has been made.

    Only the issue for THIS subject is touched. Anything else stays for the
    sweep to deal with.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from alerts import event_key, marker  # noqa: E402

    needle = marker(event_key("change-control", subject))
    issues = open_issues()
    for issue in issues:
        if needle in (issue.get("title") or ""):
            number = issue.get("number")
            body = (
                "Closed automatically: the `change-control` check for this run went "
                "green, so the decision this issue asked for has been made.\n\n"
                f"- subject: `{subject}`\n"
                f"- workflow: {os.environ.get('RUN_URL', '')}\n\n"
                "This issue was the notification of a decision that is now recorded "
                "in the workflow run. Script: `scripts/close_change_control_issues.py`."
            )
            out = _run([
                "api", "-X", "PATCH", f"repos/{REPO}/issues/{number}",
                "-f", "state=closed", "-f", f"body={body}",
            ])
            if out is None:
                print(f"  FAILED to close #{number}")
                return False
            print(f"  closed #{number} (subject {subject})")
            return True
    print(f"  no open issue for subject {subject} (nothing to close)")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would close, change nothing.")
    parser.add_argument("--subject", default=None,
                        help=("Close only the issue raised for this subject "
                              "('pr-NNN' or 'push-<ref>-<sha12>'). Used by the "
                              "add-only workflow when its check passes."))
    args = parser.parse_args(argv)

    if args.subject:
        print(f"closing change-control issue for subject: {args.subject}")
        return 0 if close_for_subject(args.subject) else 1

    issues = open_issues()
    print(f"open {LABEL} issues: {len(issues)}")

    tally = {"close": 0, "keep": 0, "unapproved": 0, "unknown": 0}
    for issue in issues:
        verdict = classify(issue)
        tally[verdict["verdict"]] = tally.get(verdict["verdict"], 0) + 1
        print(f"  #{verdict['number']:<4} {verdict['kind']:<8} "
              f"{verdict['verdict']:<11} {verdict['reason']}")
        if verdict["verdict"] == "close" and not args.dry_run:
            if close_issue(verdict["number"], verdict["reason"]):
                print(f"    closed #{verdict['number']}")
            else:
                print(f"    FAILED to close #{verdict['number']}")

    print(f"\nsummary: {tally}")
    if tally.get("unapproved"):
        print("unapproved mutations that landed: "
              f"{tally['unapproved']} (left OPEN on purpose -- read these)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
