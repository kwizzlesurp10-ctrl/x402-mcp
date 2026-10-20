"""Warden guardrails: load ledger/policy.json and vet upstream purchases.

Enforces the spend caps and network/domain rules the repo already documents in
ledger/policy.json, plus running daily/monthly totals derived from the spend
ledger so an autonomous buyer cannot drain the wallet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from app import ledger_io

_DEFAULT_POLICY = {
    "max_price_per_call_usdc": 0.05,
    "daily_cap_usdc": 0.50,
    "monthly_cap_usdc": 3.00,
    "allowed_networks_mainnet": ["eip155:8453"],
    "testnet_networks": ["eip155:84532"],
    "domain_denylist": [],
    "domain_allowlist": [],
    "require_testnet_first": True,
    "receive_wallet": "0xSET_ME",
}


@dataclass
class Policy:
    max_price_per_call_usdc: float
    daily_cap_usdc: float
    monthly_cap_usdc: float
    allowed_networks_mainnet: list[str] = field(default_factory=list)
    testnet_networks: list[str] = field(default_factory=list)
    domain_denylist: list[str] = field(default_factory=list)
    domain_allowlist: list[str] = field(default_factory=list)
    require_testnet_first: bool = True
    receive_wallet: str = "0xSET_ME"


def load_policy() -> Policy:
    """Read ledger/policy.json, falling back to conservative defaults."""
    path = ledger_io.LEDGER / "policy.json"
    data = dict(_DEFAULT_POLICY)
    try:
        if path.exists():
            data.update(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        pass
    return Policy(
        max_price_per_call_usdc=float(data["max_price_per_call_usdc"]),
        daily_cap_usdc=float(data["daily_cap_usdc"]),
        monthly_cap_usdc=float(data["monthly_cap_usdc"]),
        allowed_networks_mainnet=list(data.get("allowed_networks_mainnet", [])),
        testnet_networks=list(data.get("testnet_networks", [])),
        domain_denylist=list(data.get("domain_denylist", [])),
        domain_allowlist=list(data.get("domain_allowlist", [])),
        require_testnet_first=bool(data.get("require_testnet_first", True)),
        receive_wallet=str(data.get("receive_wallet", "0xSET_ME")),
    )


def spend_totals() -> tuple[float, float]:
    """Return (spent_today_usdc, spent_this_month_usdc) from the spend ledger."""
    now = datetime.now(UTC)
    today = now.strftime("%Y-%m-%d")
    month = now.strftime("%Y-%m")
    day_total = 0.0
    month_total = 0.0
    # limit=None: aggregate the whole ledger (do not truncate); settled-only so
    # unsettled attempts never inflate the caps.
    for row in ledger_io.read_ledger_rows("spend", limit=None):
        if not row.get("settled", True):
            continue
        ts = str(row.get("ts", ""))
        amount = float(row.get("amount_usdc", 0) or 0)
        if ts.startswith(month):
            month_total += amount
        if ts.startswith(today):
            day_total += amount
    return round(day_total, 6), round(month_total, 6)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def review_purchase(
    policy: Policy,
    *,
    url: str,
    price_usdc: float | None,
    network: str | None,
    spent_today: float,
    spent_month: float,
) -> str | None:
    """Return a veto reason string, or None if the purchase is approved.

    spent_today/spent_month include prior approvals in the current run so
    cumulative caps hold across a batch of buys.
    """
    if price_usdc is None:
        return "unknown price — cannot guarantee per-call cap"
    if price_usdc > policy.max_price_per_call_usdc:
        return (
            f"price ${price_usdc:.4f} exceeds max_price_per_call "
            f"${policy.max_price_per_call_usdc:.4f}"
        )
    if spent_today + price_usdc > policy.daily_cap_usdc:
        return (
            f"would breach daily cap: ${spent_today:.4f} + ${price_usdc:.4f} "
            f"> ${policy.daily_cap_usdc:.4f}"
        )
    if spent_month + price_usdc > policy.monthly_cap_usdc:
        return (
            f"would breach monthly cap: ${spent_month:.4f} + ${price_usdc:.4f} "
            f"> ${policy.monthly_cap_usdc:.4f}"
        )

    host = _host(url)
    if not host:
        return "unparseable URL host"
    if policy.domain_denylist and any(host.endswith(d) for d in policy.domain_denylist):
        return f"host {host} is on the domain denylist"
    if policy.domain_allowlist and not any(
        host.endswith(d) for d in policy.domain_allowlist
    ):
        return f"host {host} is not on the domain allowlist"

    if network and policy.require_testnet_first:
        is_testnet = network in policy.testnet_networks
        is_mainnet = network in policy.allowed_networks_mainnet
        if not is_testnet and is_mainnet:
            return (
                f"require_testnet_first: refusing mainnet network {network} "
                "before a testnet run"
            )
    return None
