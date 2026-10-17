"""Revenue-row quality classification: what counts as real revenue.

The revenue ledger is append-only and is NEVER rewritten here. Instead every
row is classified at read time, so the dashboard and reports can count only
verified Base-mainnet settlements from external buyers while the raw rows stay
intact and auditable. Removing an entry from app/revenue_exclusions.json, or
reverting this module, restores the previous numbers; nothing is deleted.

Qualities (first match wins):

- ``unsettled``          settled is false
- ``testnet``            network is not exactly the counted network
                         (eip155:8453 in production; see counted_network())
- ``network_unverified`` network field is a multi-network config string
- ``test_tx``            tx is not a 0x + 64-hex transaction hash (0xdeadbeef,
                         0xabc, 0xcatalog0, None, "0x0x…", …): fixtures/placeholders
- ``excluded``           tx listed in app/revenue_exclusions.json (audited:
                         no USDC transfer to a project payTo in that tx)
- ``duplicate``          the same tx hash already counted earlier
- ``self_payment``       payer is an operator wallet / project payTo / own key
- ``unknown_payer``      no payer recorded; never assumed external
- ``verified_external``  everything else: real hash, Base mainnet, external payer

Only ``verified_external`` counts toward revenue.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app import ledger_io

BASE_MAINNET = "eip155:8453"
TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

# Every address this project has used as payTo (current + retired cashiers).
# A sale "from" one of these is the operator paying itself.
PROJECT_PAYTO_ADDRESSES = frozenset(
    {
        "0x0d25a44f74868ece53b305c97139cf4b62963410",  # current Coinbase Wallet
        "0x05e1720bb82f86b5bc7940a99fdc702e32256357",  # retired sole cashier
        "0xab745e5f576667037696e78ba7da28e193e4423d",  # retired oracle payTo
    }
)

COUNTED_QUALITY = "verified_external"
QUALITIES = (
    "unsettled",
    "test_tx",
    "testnet",
    "network_unverified",
    "excluded",
    "duplicate",
    "self_payment",
    "unknown_payer",
    COUNTED_QUALITY,
)

EXCLUSIONS_PATH = Path(__file__).with_name("revenue_exclusions.json")


def counted_network() -> str:
    """The one network whose settlements count: the deployment's primary CAIP-2.

    Production (X402_DEFAULT_NETWORK=eip155:8453, possibly comma-joined with
    other rails) counts only Base mainnet. A Sepolia dev box counts Sepolia so
    local dashboards still move; it never counts mainnet-only labels it can't
    have earned.
    """
    from app.config import settings

    first = str(settings.x402_default_network or BASE_MAINNET).split(",")[0].strip()
    return first or BASE_MAINNET


def strict_mode() -> bool:
    """True on a Base-mainnet deployment: non-sales are dropped from reports and
    the production store refuses fake/test rows."""
    return counted_network() == BASE_MAINNET


def is_tx_hash(tx: object) -> bool:
    return isinstance(tx, str) and bool(TX_HASH_RE.match(tx.strip()))


def load_exclusions(path: Path | None = None) -> dict[str, str]:
    """tx hash (lowercase) -> reason. Missing/corrupt file means no exclusions."""
    p = path or EXCLUSIONS_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for entry in data.get("exclusions", []) if isinstance(data, dict) else []:
        tx = str(entry.get("tx") or "").strip().lower()
        if tx:
            out[tx] = str(entry.get("reason") or "excluded")
    return out


def classify_revenue_row(
    row: dict[str, Any],
    *,
    operator_wallets: set[str] | None = None,
    exclusions: dict[str, str] | None = None,
    seen_txs: set[str] | None = None,
    network: str | None = None,
) -> str:
    """Return the quality label for one revenue row (see module doc)."""
    if not row.get("settled", True):
        return "unsettled"
    want = network or BASE_MAINNET
    row_network = str(row.get("network") or "").strip()
    if row_network != want:
        return "network_unverified" if "," in row_network else "testnet"
    tx = row.get("tx")
    if not is_tx_hash(tx):
        return "test_tx"
    tx_l = str(tx).strip().lower()
    if exclusions and tx_l in exclusions:
        return "excluded"
    if seen_txs is not None:
        if tx_l in seen_txs:
            return "duplicate"
        seen_txs.add(tx_l)
    payer = str(row.get("payer") or "").strip().lower()
    if payer and payer in PROJECT_PAYTO_ADDRESSES:
        return "self_payment"
    try:
        is_operator = ledger_io.classify_operator_settle(row, operator_wallets)
    except Exception:  # malformed → unknown, never external
        is_operator = None
    if is_operator is True:
        return "self_payment"
    if is_operator is None:
        return "unknown_payer"
    return COUNTED_QUALITY


def annotate_revenue_rows(
    rows: Iterable[dict[str, Any]],
    *,
    operator_wallets: set[str] | None = None,
    exclusions: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Copy rows adding ledger_quality / counts_as_revenue (input order kept).

    Duplicates are detected oldest-first so the first settlement of a tx is the
    one that counts, regardless of the newest-first display order.
    """
    rows = list(rows)
    wallets = ledger_io.operator_wallet_set() if operator_wallets is None else operator_wallets
    excl = load_exclusions() if exclusions is None else exclusions
    net = counted_network()
    seen: set[str] = set()
    labels: list[str] = [""] * len(rows)
    order = sorted(range(len(rows)), key=lambda i: str(rows[i].get("ts") or ""))
    for i in order:
        labels[i] = classify_revenue_row(
            rows[i], operator_wallets=wallets, exclusions=excl, seen_txs=seen, network=net
        )
    out = []
    for row, label in zip(rows, labels):
        a = dict(row)
        a["ledger_quality"] = label
        a["counts_as_revenue"] = label == COUNTED_QUALITY
        if label == "excluded":
            a["ledger_quality_reason"] = excl.get(str(row.get("tx")).strip().lower())
        out.append(a)
    return out


def summarize(annotated: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Before/after totals: raw ledger vs verified external revenue."""
    by_quality: dict[str, dict[str, float]] = {
        q: {"rows": 0, "usdc": 0.0} for q in QUALITIES
    }
    raw_rows = 0
    raw_usdc = 0.0
    for row in annotated:
        amount = float(row.get("amount_usdc") or 0.0)
        raw_rows += 1
        raw_usdc += amount
        bucket = by_quality.setdefault(str(row.get("ledger_quality")), {"rows": 0, "usdc": 0.0})
        bucket["rows"] += 1
        bucket["usdc"] += amount
    verified = by_quality[COUNTED_QUALITY]
    return {
        "raw": {"rows": raw_rows, "usdc": round(raw_usdc, 6)},
        "verified_external": {"rows": int(verified["rows"]), "usdc": round(verified["usdc"], 6)},
        "excluded": {
            "rows": raw_rows - int(verified["rows"]),
            "usdc": round(raw_usdc - verified["usdc"], 6),
        },
        "by_quality": {
            q: {"rows": int(v["rows"]), "usdc": round(v["usdc"], 6)} for q, v in by_quality.items()
        },
    }


def new_revenue_row_problem(row: dict[str, Any], *, production_store: bool) -> str | None:
    """Why a new row must not be written to the production ledger, or None.

    Applied by ledger_writer before an append. The jsonl dev/test ledger stays
    permissive (fixtures use fake ids); the Redis store is production and only
    takes rows that could be a real Base-mainnet settlement.
    """
    if not production_store or not strict_mode():
        return None
    if not is_tx_hash(row.get("tx")):
        return f"tx {row.get('tx')!r} is not a transaction hash"
    if str(row.get("network") or "") != BASE_MAINNET:
        return f"network {row.get('network')!r} is not {BASE_MAINNET}"
    return None


NOT_SALES = frozenset({"unsettled", "test_tx", "testnet", "network_unverified", "excluded", "duplicate"})


def sales_rows(rows: Iterable[dict[str, Any]], *, operator_wallets: set[str] | None = None) -> list[dict[str, Any]]:
    """Rows that are sales at all (self/unknown/external), for report aggregates.

    In strict (mainnet) mode test ids, testnet, excluded and duplicate rows are
    dropped; elsewhere rows pass through unchanged so dev fixtures still work.
    """
    rows = list(rows)
    if not strict_mode():
        return rows
    return [
        r
        for r in annotate_revenue_rows(rows, operator_wallets=operator_wallets)
        if r["ledger_quality"] not in NOT_SALES
    ]
