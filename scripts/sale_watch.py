"""Scan Base USDC Transfer logs into PAY_TO for wallets that are not ours.

Public Base RPC (mainnet.base.org) 413s a 3600-block eth_getLogs. Chunk the
window and shrink on 413 / max-range errors so a cron run still overlaps.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

try:
    from alerts import Alerter, event_key
except ImportError:  # pytest: repo root is on sys.path
    from scripts.alerts import Alerter, event_key

XFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DEFAULT_CHUNK = 500
MIN_CHUNK = 50
LOOKBACK_BLOCKS = 3600
USER_AGENT = "x402-sale-watch/1.0"


class RpcHttpError(RuntimeError):
    def __init__(self, code: int, body: str):
        super().__init__(f"RPC HTTP {code}: {body[:200]}")
        self.code = code
        self.body = body


def rpc(url: str, method: str, params: object, timeout: int = 45) -> object:
    req = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"content-type": "application/json", "user-agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RpcHttpError(e.code, body) from e
    if payload.get("error"):
        err = payload["error"]
        raise RuntimeError(f"RPC {method} error: {err}")
    return payload["result"]


def _too_large(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        (isinstance(exc, RpcHttpError) and exc.code == 413)
        or "payload too large" in text
        or "query returned more than" in text
        or "block range" in text
        or "response size" in text
        or "log response size" in text
    )


def fetch_logs_chunked(
    rpc_fn,
    *,
    usdc: str,
    topic_to: str,
    start: int,
    latest: int,
    chunk: int = DEFAULT_CHUNK,
) -> list[dict]:
    """eth_getLogs over [start, latest], splitting when the RPC rejects the window."""
    logs: list[dict] = []
    cur = max(0, start)
    size = max(MIN_CHUNK, chunk)
    while cur <= latest:
        end = min(cur + size - 1, latest)
        try:
            batch = rpc_fn(
                "eth_getLogs",
                [
                    {
                        "fromBlock": hex(cur),
                        "toBlock": hex(end),
                        "address": usdc,
                        "topics": [XFER, None, topic_to],
                    }
                ],
            ) or []
            logs.extend(batch)
            cur = end + 1
        except Exception as exc:
            if _too_large(exc) and size > MIN_CHUNK:
                size = max(MIN_CHUNK, size // 2)
                continue
            if _too_large(exc) and end > cur:
                size = 1
                continue
            raise
    return logs


def classify_strangers(logs: list[dict], ours: set[str]) -> list[tuple[str, float, str, int]]:
    strangers: list[tuple[str, float, str, int]] = []
    for lg in logs:
        frm = "0x" + lg["topics"][1][-40:]
        if frm.lower() in ours:
            continue
        amt = int(lg["data"], 16) / 1e6
        strangers.append((frm, amt, lg["transactionHash"], int(lg["blockNumber"], 16)))
    return strangers


def main() -> None:
    rpc_url = os.environ["RPC"]
    usdc = os.environ["USDC"]
    pay_to = os.environ["PAY_TO"].lower()
    ours = {w.strip().lower() for w in os.environ["OUR_WALLETS"].split(",") if w.strip()}
    repo = os.environ["GH_REPO"]
    topic_to = "0x" + "0" * 24 + pay_to[2:]

    def rpc_fn(method: str, params: object) -> object:
        return rpc(rpc_url, method, params)

    latest = int(rpc_fn("eth_blockNumber", []), 16)
    start = latest - LOOKBACK_BLOCKS
    logs = fetch_logs_chunked(rpc_fn, usdc=usdc, topic_to=topic_to, start=start, latest=latest)
    strangers = classify_strangers(logs, ours)
    print(
        f"scanned {latest - start} blocks; {len(logs)} payments in, {len(strangers)} from strangers"
    )

    alerter = Alerter(repo, "sale")
    for frm, amt, tx, blk in strangers:
        alerter.alert(
            event_key("sale", tx),
            f"\U0001F4B0 External sale: ${amt:.4f} USDC from {frm[:10]}…",
            "A wallet that is not ours paid the storefront.\n\n"
            f"- **Amount:** ${amt:.6f} USDC\n"
            f"- **From:** `{frm}`\n"
            f"- **To (pay_to):** `{pay_to}`\n"
            f"- **Tx:** https://basescan.org/tx/{tx}\n"
            f"- **Block:** {blk}\n\n"
            "This is a real external purchase — the first-ever was 0xadacdfdd on "
            "2026-07-22 (old $0.25 Pulse). Cross-check /ledger/revenue and /demand "
            "to see which product and client class. Close this issue once acknowledged.",
        )
    print(alerter.summary())


if __name__ == "__main__":
    main()
