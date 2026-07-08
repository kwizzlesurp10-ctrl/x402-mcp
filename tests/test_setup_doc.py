"""SETUP.md documents user-facing install, wallet, and test guidance."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "docs" / "SETUP.md"


def test_setup_doc_exists() -> None:
    assert SETUP.exists(), "docs/SETUP.md is required for user onboarding"


def test_setup_covers_wallet_and_testing() -> None:
    text = SETUP.read_text(encoding="utf-8")
    assert "X402_PAY_TO_ADDRESS" in text
    assert "EVM_PRIVATE_KEY" in text
    assert "pytest" in text
    assert "Expected errors" in text or "expected" in text.lower()
    assert "10 tools" in text or "10 MCP tools" in text