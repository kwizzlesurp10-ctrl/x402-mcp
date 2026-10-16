"""Add-only change control: existing files may not be edited, renamed, or deleted.

A hallucinating agent that "cleans up" app/ or rewrites a working endpoint is
the failure this pins. New files are allowed. Bypass is NOT an env var — agents
can set those. Bypass is the GitHub Environment `operator-approve` click.
"""

from __future__ import annotations

import json

import pytest

from scripts.add_only_guard import (
    classify,
    diff_args,
    is_add_only,
    mutation_report,
    parse_name_status,
    summarize,
)


def test_empty_diff_is_add_only() -> None:
    entries = parse_name_status("")
    assert entries == []
    assert is_add_only(entries) is True


def test_new_files_only_are_add_only() -> None:
    diff = "A\tscripts/add_only_guard.py\nA\tdocs/CHANGE-CONTROL.md\n"
    entries = parse_name_status(diff)
    adds, mutations = classify(entries)
    assert [e.path for e in adds] == [
        "scripts/add_only_guard.py",
        "docs/CHANGE-CONTROL.md",
    ]
    assert mutations == []
    assert is_add_only(entries) is True


def test_modifying_an_existing_file_is_a_mutation() -> None:
    entries = parse_name_status("M\tapp/main.py\n")
    _adds, mutations = classify(entries)
    assert [e.path for e in mutations] == ["app/main.py"]
    assert is_add_only(entries) is False


def test_deleting_an_existing_file_is_a_mutation() -> None:
    entries = parse_name_status("D\tapp/commerce.py\n")
    assert is_add_only(entries) is False
    assert "app/commerce.py" in mutation_report(entries)


def test_rename_is_a_mutation_even_if_a_new_path_appears() -> None:
    """Agents love 'move to a better name' — that deletes the old path."""
    entries = parse_name_status("R100\tapp/main.py\tapp/server.py\n")
    assert len(entries) == 1
    assert entries[0].status == "R"
    assert entries[0].path == "app/server.py"
    assert entries[0].orig_path == "app/main.py"
    assert is_add_only(entries) is False


def test_copy_and_typechange_are_mutations() -> None:
    copy = parse_name_status("C075\tapp/config.py\tapp/config_copy.py\n")
    typ = parse_name_status("T\tscripts/settle_once.py\n")
    assert is_add_only(copy) is False
    assert is_add_only(typ) is False


def test_add_plus_modify_is_still_a_mutation() -> None:
    entries = parse_name_status(
        "A\ttests/test_new.py\nM\tapp/config.py\nA\tdocs/notes.md\n"
    )
    adds, mutations = classify(entries)
    assert [e.path for e in adds] == ["tests/test_new.py", "docs/notes.md"]
    assert [e.path for e in mutations] == ["app/config.py"]
    assert is_add_only(entries) is False


def test_env_var_cannot_bypass_the_classifier() -> None:
    """Agents can export OPERATOR_APPROVED=1. The parser must ignore it."""
    entries = parse_name_status("M\tapp/main.py\n")
    assert is_add_only(entries, extra_env={"OPERATOR_APPROVED": "1"}) is False
    assert is_add_only(entries, extra_env={"AGENT_APPROVED": "true"}) is False


def test_summarize_json_marks_mutation_true() -> None:
    entries = parse_name_status("M\tapp/main.py\nA\tNEW.md\n")
    payload = json.loads(summarize(entries))
    assert payload["mutation"] is True
    assert payload["adds"] == ["NEW.md"]
    assert payload["mutations"] == [{"status": "M", "path": "app/main.py"}]


def test_summarize_json_marks_add_only() -> None:
    entries = parse_name_status("A\tNEW.md\n")
    payload = json.loads(summarize(entries))
    assert payload["mutation"] is False
    assert payload["adds"] == ["NEW.md"]
    assert payload["mutations"] == []


def test_diff_args_uses_triple_dot_base_by_default() -> None:
    assert diff_args()[-1] == "origin/master...HEAD"
    assert diff_args(base="origin/main")[-1] == "origin/main...HEAD"


def test_diff_args_range_overrides_base_so_push_to_master_cannot_hide() -> None:
    """After a push, origin/master...HEAD is empty. CI must pass BEFORE...SHA."""
    cmd = diff_args(base="origin/master", rev_range="abc123...def456")
    assert cmd[-1] == "abc123...def456"
    assert "--find-renames" in cmd
