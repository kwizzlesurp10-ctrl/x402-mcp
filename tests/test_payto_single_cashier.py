"""Canonical payTo must be one cashier — no stale bounty/docs split-brain."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.agent_surface import DEFAULT_PAY_TO
from app.config import Settings
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)

# Sole live seller cashier. Discovery, 402, Smithery, and Render must agree.
CANONICAL_PAY_TO = "0x0d25A44f74868eCE53B305C97139CF4B62963410"

# Former receive addresses. Paying either does not credit the live cashier.
RETIRED_PAY_TO_PREFIXES = (
    "0xAB745e5F",  # pre-2026-09 retired bounty / Smithery default
    "0xcA6791f9",  # leaked cold-receive.key / Render dashboard drift
    "0x8A897D54",  # prior live cashier rotated 2026-09-20
    "0x9138fEA6",  # leaked buyer-hot.key
    "0x05e1720b",  # prior live cashier rotated 2026-10-17
)

PUBLIC_SURFACES = (
    ROOT / "MEMORY.md",
    ROOT / "README.md",
    ROOT / "docs" / "BOUNTIES.md",
    ROOT / ".github" / "FUNDING.yml",
    ROOT / ".github" / "ISSUE_TEMPLATE" / "paid-bounty.md",
    ROOT / "smithery.yaml",
    ROOT / "render.yaml",
    ROOT / ".env.example",
    ROOT / "deployment" / "seller.env.example",
    ROOT / "docs" / "wallet-split-and-bazaar.md",
)


def test_pay_to_strips_render_dashboard_whitespace() -> None:
    dirty = CANONICAL_PAY_TO + " \n"
    parsed = Settings.model_validate({"x402_pay_to_address": dirty})
    assert parsed.x402_pay_to_address == CANONICAL_PAY_TO
    assert len(parsed.x402_pay_to_address) == 42
    blank = Settings.model_validate({"x402_pay_to_address": " \n"})
    assert blank.x402_pay_to_address is None


def test_default_pay_to_is_the_canonical_cashier() -> None:
    assert DEFAULT_PAY_TO == CANONICAL_PAY_TO
    assert DEFAULT_PAY_TO.startswith("0x")
    assert len(DEFAULT_PAY_TO) == 42
    lowered = DEFAULT_PAY_TO.lower()
    for prefix in RETIRED_PAY_TO_PREFIXES:
        assert prefix.lower() not in lowered


def test_public_docs_cite_the_live_cashier_not_the_retired_one() -> None:
    for path in PUBLIC_SURFACES:
        text = path.read_text(encoding="utf-8")
        assert DEFAULT_PAY_TO in text, f"{path.name} missing live payTo {DEFAULT_PAY_TO}"
        for prefix in RETIRED_PAY_TO_PREFIXES:
            assert prefix not in text, f"{path.name} still cites retired payTo {prefix}"


def test_smithery_default_pay_to_is_canonical() -> None:
    doc = yaml.safe_load((ROOT / "smithery.yaml").read_text(encoding="utf-8"))
    default = doc["configSchema"]["properties"]["X402_PAY_TO_ADDRESS"]["default"]
    assert default == DEFAULT_PAY_TO
    assert doc["exampleConfig"]["X402_PAY_TO_ADDRESS"] == DEFAULT_PAY_TO


def test_render_blueprint_pins_canonical_pay_to() -> None:
    """payTo is public. Pinning it in the blueprint stops dashboard drift."""
    doc = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    env = doc["services"][0]["envVars"]
    pay = next(item for item in env if item["key"] == "X402_PAY_TO_ADDRESS")
    assert pay.get("value") == DEFAULT_PAY_TO
    assert pay.get("sync") is not False


def test_tracked_tree_does_not_advertise_retired_pay_to() -> None:
    """Bounty hunters grep GitHub; a leftover retired prefix is a wrong cashier."""
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
        posix = Path(rel).as_posix()
        if posix == self_rel:
            continue
        if posix == "CHANGES.md":
            continue
        if posix.startswith(".keys/"):
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
        for prefix in RETIRED_PAY_TO_PREFIXES:
            if prefix in text:
                offenders.append(f"{rel} ({prefix})")
                break
    assert offenders == [], f"retired payTo still present in: {offenders}"


def test_funding_json_pay_to_is_the_canonical_cashier() -> None:
    body = client.get("/.well-known/funding.json").json()
    assert body["payTo"] == DEFAULT_PAY_TO


def test_agent_card_funding_pay_to_is_the_canonical_cashier() -> None:
    body = client.get("/.well-known/agent-card.json").json()
    assert body["funding"]["payTo"] == DEFAULT_PAY_TO
