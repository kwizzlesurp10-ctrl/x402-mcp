"""Docker evidence contract — saved manifest JSON must list all 10 tools."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.test_mcp_tools import EXPECTED_TOOLS

SCRATCH = Path(
    os.environ.get(
        "GOAL_SCRATCH",
        r"C:\Users\Keith\AppData\Local\Temp\grok-goal-96e31bb2e41a\implementer",
    )
)


@pytest.mark.parametrize("boot", [1, 2])
def test_manifest_boot_evidence_lists_all_tools(boot: int) -> None:
    path = SCRATCH / f"manifest_boot{boot}.json"
    if not path.exists():
        pytest.skip(f"missing {path.name} — run scripts/capture_goal_evidence.py first")
    data = json.loads(path.read_text(encoding="utf-8"))
    names = {tool["name"] for tool in data.get("tools", [])}
    missing = EXPECTED_TOOLS - names
    assert not missing, f"boot {boot} manifest missing tools: {sorted(missing)}"


@pytest.mark.parametrize("boot", [1, 2])
def test_health_boot_evidence_service_id(boot: int) -> None:
    path = SCRATCH / f"health_boot{boot}.json"
    if not path.exists():
        pytest.skip(f"missing {path.name} — run scripts/capture_goal_evidence.py first")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("service") == "x402-micropayments-mcp"