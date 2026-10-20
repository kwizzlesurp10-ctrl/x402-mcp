"""The watcher alert path must be silent on the second sighting of an event.

thread-watch opened 432 duplicate issues because its dedup fingerprint was
never written into the issue it created, so no query could ever find it. These
tests pin the three properties that failure taught us: the key round-trips
through a real title, a repeat opens nothing, and no alert can `@`-mention a
stranger.
"""

from __future__ import annotations

import json

import pytest

from scripts.alerts import (
    MAX_ALERTS_PER_RUN,
    Alerter,
    defuse_mentions,
    event_key,
    keys_in,
    marker,
)


class FakeGh:
    """Stands in for the `gh` CLI: records creates, replays them as the list."""

    def __init__(self, existing_titles: list[str] | None = None, fail: str | None = None):
        self.titles = list(existing_titles or [])
        self.created: list[dict[str, str]] = []
        self.fail = fail  # "list" or "create" to simulate a gh failure
        self.list_calls = 0

    def __call__(self, args: list[str]) -> str | None:
        if args[1] == "list":
            self.list_calls += 1
            if self.fail == "list":
                return None
            return json.dumps([{"title": t} for t in self.titles])
        if args[1] == "create":
            if self.fail == "create":
                return None
            flags = {args[i]: args[i + 1] for i in range(0, len(args) - 1)}
            self.created.append({"title": flags["--title"], "body": flags["--body"]})
            self.titles.append(flags["--title"])
            return "https://github.test/issues/1\n"
        raise AssertionError(f"unexpected gh call: {args}")


def _alerter(gh: FakeGh) -> Alerter:
    a = Alerter("owner/repo", "outreach")
    a._run = gh  # type: ignore[method-assign]
    return a


def test_the_key_a_run_writes_is_the_key_the_next_run_finds() -> None:
    """The regression itself: the fingerprint has to survive into the title."""
    gh = FakeGh()
    key = event_key("thread-evt", "owner/repo#58", "comment", "IC_123")

    assert _alerter(gh).alert(key, "reply on the outreach thread", "body") is True

    # A fresh run — new process, new Alerter, only GitHub as memory.
    second = _alerter(FakeGh(existing_titles=gh.titles))
    assert second.alert(key, "reply on the outreach thread", "body") is False
    assert second.opened == 0


def test_the_same_event_hashes_the_same_and_a_different_one_does_not() -> None:
    assert event_key("a", "b") == event_key("a", "b")
    assert event_key("a", "b") != event_key("ab", "")
    assert marker(event_key("a", "b")) in f"title {marker(event_key('a', 'b'))}"


def test_keys_are_read_back_out_of_real_titles() -> None:
    key = event_key("x")
    assert keys_in([f"\U0001F4AC repo#58: reply {marker(key)}", "unrelated issue"]) == {key}
    assert keys_in([None, ""]) == set()  # type: ignore[list-item]


def test_no_alert_can_mention_a_stranger() -> None:
    gh = FakeGh()
    _alerter(gh).alert(
        event_key("evt"),
        "reply from @haustorium12",
        "- **By:** @haustorium12\n\n> thanks @someone-else, see @a-b\n",
    )
    created = gh.created[0]
    assert "@haustorium12" not in created["title"].replace("`@haustorium12`", "")
    assert "`@haustorium12`" in created["title"]
    for handle in ("@haustorium12", "@someone-else", "@a-b"):
        assert f"`{handle}`" in created["body"]
        # every raw occurrence is inside a code span
        assert created["body"].count(handle) == created["body"].count(f"`{handle}`")


def test_an_email_address_is_not_mangled() -> None:
    assert defuse_mentions("mail vicky@blockrun.ai today") == "mail vicky@blockrun.ai today"


def test_a_runaway_watcher_is_capped_not_unlimited() -> None:
    gh = FakeGh()
    a = _alerter(gh)
    for i in range(MAX_ALERTS_PER_RUN + 4):
        a.alert(event_key("runaway", i), f"event {i}", "body")
    assert a.opened == MAX_ALERTS_PER_RUN
    assert a.suppressed == 4
    assert len(gh.created) == MAX_ALERTS_PER_RUN


def test_a_watcher_that_cannot_read_its_history_alerts_nothing() -> None:
    """Blind is not the same as new — the old code's failure-open is what spammed."""
    gh = FakeGh(fail="list")
    a = _alerter(gh)
    assert a.alert(event_key("evt"), "title", "body") is False
    assert gh.created == []


def test_history_is_read_once_per_run_not_once_per_event() -> None:
    gh = FakeGh()
    a = _alerter(gh)
    for i in range(3):
        a.alert(event_key("e", i), f"event {i}", "body")
    assert gh.list_calls == 1


def test_a_failed_create_is_not_counted_as_alerted() -> None:
    gh = FakeGh(fail="create")
    a = _alerter(gh)
    assert a.alert(event_key("evt"), "title", "body") is False
    assert a.opened == 0


@pytest.mark.parametrize("workflow", ["thread-watch", "task-watch", "sale-watch"])
def test_every_watcher_workflow_uses_this_module(workflow: str) -> None:
    """No watcher gets to hand-roll dedup again."""
    from pathlib import Path

    text = Path(__file__).resolve().parents[1].joinpath(
        ".github/workflows", f"{workflow}.yml"
    ).read_text(encoding="utf-8")
    assert "from alerts import" in text or "from scripts.alerts import" in text
    assert "--search" not in text, "dedup by search is what broke; list by label instead"
