"""Canonical payTo must be one cashier — no stale bounty/docs split-brain."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.agent_surface import DEFAULT_PAY_TO
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)

# Retired receive address. Paying it does not credit the live Base cashier.
RETIRED_PAY_TO_PREFIX = "0xAB745e5F"

PUBLIC_SURFACES = (
    ROOT / "MEMORY.md",
    ROOT / "README.md",
    ROOT / "docs" / "BOUNTIES.md",
    ROOT / ".github" / "FUNDING.yml",
    ROOT / ".github" / "ISSUE_TEMPLATE" / "paid-bounty.md",
)


def test_default_pay_to_is_a_base_address() -> None:
    assert DEFAULT_PAY_TO.startswith("0x")
    assert len(DEFAULT_PAY_TO) == 42
    assert RETIRED_PAY_TO_PREFIX.lower() not in DEFAULT_PAY_TO.lower()


def test_public_docs_cite_the_live_cashier_not_the_retired_one() -> None:
    for path in PUBLIC_SURFACES:
        text = path.read_text(encoding="utf-8")
        assert DEFAULT_PAY_TO in text, f"{path.name} missing live payTo {DEFAULT_PAY_TO}"
        assert RETIRED_PAY_TO_PREFIX not in text, f"{path.name} still cites retired payTo"


def test_tracked_tree_does_not_advertise_retired_pay_to() -> None:
    """Bounty hunters grep GitHub; a leftover 0xAB745e5F is a wrong cashier."""
    import subprocess

    listed = subprocess.check_output(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).splitlines()
    self_rel = Path(__file__).resolve().relative_to(ROOT).as_posix()
    offenders: list[str] = []
    for rel in listed:
        if Path(rel).as_posix() == self_rel:
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        if path.suffix.lower() in {".png", ".jpg", ".webp", ".woff", ".woff2", ".map"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if RETIRED_PAY_TO_PREFIX in text:
            offenders.append(rel)
    assert offenders == [], f"retired payTo still present in: {offenders}"


def test_funding_json_pay_to_is_the_canonical_cashier() -> None:
    body = client.get("/.well-known/funding.json").json()
    assert body["payTo"] == DEFAULT_PAY_TO


def test_agent_card_funding_pay_to_is_the_canonical_cashier() -> None:
    body = client.get("/.well-known/agent-card.json").json()
    assert body["funding"]["payTo"] == DEFAULT_PAY_TO
