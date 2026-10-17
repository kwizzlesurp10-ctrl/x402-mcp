"""Base JSON-RPC helpers for the sale-watch GitHub Action.

Retries transient failures, rotates across public Base endpoints, and chunks
eth_getLogs to reduce rate-limit pressure on scheduled runs.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from typing import Any, Callable

DEFAULT_RPCS: tuple[str, ...] = (
    "https://mainnet.base.org",
    "https://base.llamarpc.com",
    "https://base-rpc.publicnode.com",
    "https://1rpc.io/base",
)

MAX_ATTEMPTS_PER_URL = 5
USER_AGENT = "x402-sale-watch/1.0"
MIN_LOG_CHUNK = 25
DEFAULT_LOG_CHUNK = 900

TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)


class RpcInfrastructureError(Exception):
    """Every configured RPC endpoint failed with retryable errors (e.g. 429)."""


class RpcClientError(Exception):
    """Non-retryable RPC or HTTP failure (bad request, auth, malformed response)."""


def rpc_endpoint_urls() -> list[str]:
    ordered: list[str] = []
    for candidate in (
        os.environ.get("BASE_RPC_URL", "").strip(),
        os.environ.get("RPC", "").strip(),
        *DEFAULT_RPCS,
    ):
        if candidate and candidate not in ordered:
            ordered.append(candidate)
    return ordered


def _retry_after_seconds(headers: Any) -> float | None:
    if headers is None:
        return None
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _backoff_seconds(attempt: int, headers: Any = None) -> float:
    honored = _retry_after_seconds(headers)
    if honored is not None:
        return honored
    return min(60.0, (2 ** attempt) + random.uniform(0.0, 1.0))


def _is_retryable_http(code: int) -> bool:
    return code == 429 or code >= 500


def _json_rpc_is_rate_limited(error: dict[str, Any]) -> bool:
    code = error.get("code")
    message = str(error.get("message", "")).lower()
    if code in (-32005, -32016, 429):
        return True
    return "rate" in message or "too many" in message


def rpc_call(
    method: str,
    params: list[Any],
    *,
    endpoints: list[str] | None = None,
    timeout: float = 45.0,
) -> Any:
    urls = endpoints or rpc_endpoint_urls()
    if not urls:
        raise RpcClientError("no RPC endpoints configured")

    last_error: str = "unknown"
    for url in urls:
        for attempt in range(MAX_ATTEMPTS_PER_URL):
            try:
                request = urllib.request.Request(
                    url,
                    data=json.dumps(
                        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
                    ).encode(),
                    headers={
                        "content-type": "application/json",
                        "user-agent": USER_AGENT,
                    },
                )
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read())
            except urllib.error.HTTPError as exc:
                if exc.code == 413:
                    raise
                if not _is_retryable_http(exc.code):
                    raise RpcClientError(
                        f"RPC HTTP {exc.code} from {url} for {method}: {exc.reason}"
                    ) from exc
                last_error = f"HTTP {exc.code} from {url}"
                delay = _backoff_seconds(attempt, exc.headers)
                print(
                    f"rpc {method} {url} -> {exc.code}; "
                    f"attempt {attempt + 1}/{MAX_ATTEMPTS_PER_URL}; sleep {delay:.1f}s"
                )
                time.sleep(delay)
                continue
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if isinstance(exc, json.JSONDecodeError):
                    raise RpcClientError(f"invalid JSON from {url}") from exc
                last_error = f"{type(exc).__name__} from {url}: {exc}"
                delay = _backoff_seconds(attempt)
                print(
                    f"rpc {method} {url} -> {last_error}; "
                    f"attempt {attempt + 1}/{MAX_ATTEMPTS_PER_URL}; sleep {delay:.1f}s"
                )
                time.sleep(delay)
                continue

            if "error" in payload and payload["error"]:
                err = payload["error"]
                if _json_rpc_is_rate_limited(err):
                    last_error = f"JSON-RPC rate limit from {url}: {err}"
                    delay = _backoff_seconds(attempt)
                    print(
                        f"rpc {method} {url} -> rate limited; "
                        f"attempt {attempt + 1}/{MAX_ATTEMPTS_PER_URL}; sleep {delay:.1f}s"
                    )
                    time.sleep(delay)
                    continue
                raise RpcClientError(f"RPC error from {url}: {err}")

            return payload["result"]

        print(f"exhausted {MAX_ATTEMPTS_PER_URL} attempts on {url}; rotating endpoint")

    raise RpcInfrastructureError(f"all RPC endpoints failed ({last_error})")


def pay_to_transfer_topic(pay_to: str) -> str:
    normalized = pay_to.lower()
    if not normalized.startswith("0x") or len(normalized) != 42:
        raise RpcClientError(f"invalid PAY_TO address: {pay_to}")
    return "0x" + "0" * 24 + normalized[2:]


def fetch_transfer_logs(
    rpc: Callable[[str, list[Any]], Any],
    *,
    usdc: str,
    pay_to: str,
    start_block: int,
    end_block: int,
    chunk_size: int = DEFAULT_LOG_CHUNK,
) -> list[dict[str, Any]]:
    """Fetch ERC-20 Transfer logs to pay_to, chunking the block range."""
    if start_block > end_block:
        return []

    topic_to = pay_to_transfer_topic(pay_to)
    logs: list[dict[str, Any]] = []
    current = start_block
    size = max(MIN_LOG_CHUNK, chunk_size)

    while current <= end_block:
        to_block = min(end_block, current + size - 1)
        filter_params = {
            "fromBlock": hex(current),
            "toBlock": hex(to_block),
            "address": usdc,
            "topics": [TRANSFER_TOPIC, None, topic_to],
        }
        try:
            chunk = rpc("eth_getLogs", [filter_params])
        except urllib.error.HTTPError as exc:
            if exc.code == 413 and size > MIN_LOG_CHUNK:
                size = max(MIN_LOG_CHUNK, size // 2)
                print(
                    f"eth_getLogs 413 for blocks {current}-{to_block}; "
                    f"retrying with chunk_size={size}"
                )
                continue
            raise
        except RpcInfrastructureError:
            if size > MIN_LOG_CHUNK:
                size = max(MIN_LOG_CHUNK, size // 2)
                print(
                    f"eth_getLogs rate limited for blocks {current}-{to_block}; "
                    f"retrying with chunk_size={size}"
                )
                continue
            raise

        if chunk is None:
            chunk = []
        if not isinstance(chunk, list):
            raise RpcClientError(f"unexpected eth_getLogs result type: {type(chunk)!r}")

        logs.extend(chunk)
        current = to_block + 1

    return logs


def latest_block_number(rpc: Callable[[str, list[Any]], Any]) -> int:
    return int(rpc("eth_blockNumber", []), 16)
