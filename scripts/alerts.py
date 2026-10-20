"""Dedup-safe GitHub issue alerts for the off-box watcher workflows.

Every watcher (sale, thread, task) deliberately re-scans an overlapping window
on each run so a delayed or skipped run cannot miss an event. That only works
if the second sighting of an event is silent.

The first design put an event fingerprint into a `gh issue list --search`
query but never wrote that fingerprint into the issue it created, so the
search matched nothing, every run looked like a first sighting, and
thread-watch opened the same two alerts every 30 minutes for days — 432 issues,
each one carrying an `@`-mention of a third-party maintainer who then got 432
notifications and opened an issue here asking us to stop.

Three rules come out of that, and this module is where they live so no watcher
can quietly skip one:

1. The dedup key is written into the issue TITLE as ``[evt:<hash>]`` and is
   matched by LISTING the label's issues, never by full-text search. The list
   API is immediately consistent; the search index is not, and a fingerprint
   that is not in the issue can never be found by any query.
2. Alerts never `@`-mention anyone. Logins and quoted text are escaped into
   code spans, which GitHub renders but does not notify on. A watcher that
   misfires should waste our own attention, never a stranger's.
3. ``MAX_ALERTS_PER_RUN`` caps a single run. A watcher that suddenly wants to
   open dozens of issues is malfunctioning, not busy; past the cap it opens
   nothing more and says so in the log, so the next bug of this shape costs a
   handful of issues instead of hundreds.

Pure stdlib on purpose: this runs on a bare GitHub runner with `gh` and
python3, no install step.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess

# One run should never need more than a few alerts. Anything past this is a bug
# in the caller, and the cap is what keeps that bug cheap.
MAX_ALERTS_PER_RUN = 5

_MARKER_RE = re.compile(r"\[evt:([0-9a-f]{10})\]")
# A leading @ that GitHub would turn into a notification. Matches the login
# shape GitHub itself allows (alphanumeric plus internal hyphens). The
# lookbehind keeps the local part of an email address from making its domain
# look like a handle (vicky@blockrun.ai).
_MENTION_RE = re.compile(r"(?<![\w.-])@([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)")


def event_key(*parts: object) -> str:
    """Stable short id for one event — the same event always hashes the same.

    Parts are joined with a separator that cannot occur in the values, so
    ("a", "bc") and ("ab", "c") are different events.
    """
    joined = "\x1f".join(str(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:10]


def marker(key: str) -> str:
    """The token embedded in a title so a later run can recognise the event."""
    return f"[evt:{key}]"


def keys_in(titles: list[str]) -> set[str]:
    """Every event key already recorded in these issue titles."""
    return {m for t in titles for m in _MARKER_RE.findall(t or "")}


def defuse_mentions(text: str) -> str:
    """Neutralise `@handle` so quoting a comment cannot notify third parties.

    Wrapping in a code span keeps the handle readable and linkable-by-hand
    while GitHub stops treating it as a mention. Emails are left alone: their
    `@` is not preceded by a word boundary that GitHub parses as a mention.
    """
    return _MENTION_RE.sub(lambda m: f"`@{m.group(1)}`", text or "")


class Alerter:
    """Opens at most one issue per event, per label, ever.

    Loads the already-alerted keys once per run (one API call, not one per
    event) and treats a failed load as "alert nothing" rather than "alert
    everything" — a run that cannot read its own history has no way to tell a
    new event from the one it alerted 200 times already.
    """

    def __init__(self, repo: str, label: str, limit: int = 400) -> None:
        self.repo = repo
        self.label = label
        self.limit = limit
        self.opened = 0
        self.suppressed = 0
        self._seen: set[str] | None = None
        self.readable = True

    def _run(self, args: list[str]) -> str | None:
        r = subprocess.run(["gh", *args], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  gh {' '.join(args)} -> {r.stderr.strip()[:200]}")
            return None
        return r.stdout

    def seen(self) -> set[str]:
        if self._seen is None:
            out = self._run(
                ["issue", "list", "--repo", self.repo, "--label", self.label,
                 "--state", "all", "--limit", str(self.limit), "--json", "title"]
            )
            if out is None:
                self.readable = False
                self._seen = set()
            else:
                try:
                    self._seen = keys_in([row.get("title", "") for row in json.loads(out or "[]")])
                except json.JSONDecodeError:
                    self.readable = False
                    self._seen = set()
        return self._seen

    def alert(self, key: str, title: str, body: str) -> bool:
        """Open an issue for `key` unless it is a repeat, capped, or blind.

        Returns True only when an issue was actually created.
        """
        seen = self.seen()
        if not self.readable:
            print(f"  cannot read alert history; not alerting: {key}")
            return False
        if key in seen:
            print(f"  already alerted: {key}")
            return False
        if self.opened >= MAX_ALERTS_PER_RUN:
            self.suppressed += 1
            print(f"  cap of {MAX_ALERTS_PER_RUN} alerts/run reached; suppressed: {key}")
            return False

        full_title = f"{defuse_mentions(title)} {marker(key)}"
        out = self._run(
            ["issue", "create", "--repo", self.repo, "--title", full_title,
             "--body", defuse_mentions(body), "--label", self.label]
        )
        if out is None:
            return False
        # Record it locally too: two events in one run must not both alert if
        # they somehow share a key.
        self.seen().add(key)
        self.opened += 1
        print(f"  ALERTED: {key}")
        return True

    def summary(self) -> str:
        note = f"; {self.suppressed} suppressed by the per-run cap" if self.suppressed else ""
        return f"{self.opened} alert(s) opened{note}"
