"""Mission-control health checks — CLI and GET /doctor."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

import httpx

from app import commerce, ledger_store, redis_client
from app.config import settings
from app.swarm.registry import swarm_registry

ROOT = Path(__file__).resolve().parents[1]

CheckStatus = Literal["pass", "fail", "warn", "skip"]


def _check(
    check_id: str,
    name: str,
    status: CheckStatus,
    message: str,
    fix: str | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "name": name,
        "status": status,
        "message": message,
        "fix": fix,
    }


def _ping_url(url: str, *, timeout: float = 8.0) -> tuple[bool, str]:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
        if response.status_code < 500:
            return True, f"HTTP {response.status_code}"
        return False, f"HTTP {response.status_code}"
    except Exception as exc:
        return False, str(exc)


def _ping_rpc(url: str, *, timeout: float = 8.0) -> tuple[bool, str]:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}
            )
        if response.status_code < 500:
            return True, f"HTTP {response.status_code}"
        return False, f"HTTP {response.status_code}"
    except Exception as exc:
        return False, str(exc)


def _read_mcp_server_keys() -> dict[str, Any] | None:
    for path in (ROOT / ".mcp.json", ROOT / ".mcp.json.example"):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                servers = data.get("mcpServers", {})
                if isinstance(servers, dict):
                    return servers
            except json.JSONDecodeError:
                continue
    return None


def _agent_tool_prefixes() -> set[str]:
    agents_dir = ROOT / ".claude" / "agents"
    prefixes: set[str] = set()
    if not agents_dir.exists():
        return prefixes
    pattern = re.compile(r"mcp__([a-zA-Z0-9_]+)__")
    for path in agents_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        prefixes.update(pattern.findall(text))
    return prefixes


def run_checks() -> dict[str, Any]:
    """Synchronous doctor checks for HTTP route and CLI."""
    checks: list[dict[str, Any]] = []

    env_path = ROOT / ".env"
    if env_path.exists():
        checks.append(
            _check(
                "env_file",
                ".env present",
                "pass",
                f"Found {env_path.name}",
            )
        )
    else:
        checks.append(
            _check(
                "env_file",
                ".env present",
                "warn",
                "No .env file — using defaults only",
                "cp .env.example .env",
            )
        )

    if settings.x402_pay_to_address:
        checks.append(
            _check(
                "pay_to",
                "Receive wallet",
                "pass",
                f"X402_PAY_TO_ADDRESS set ({settings.x402_pay_to_address[:10]}…)",
            )
        )
    else:
        checks.append(
            _check(
                "pay_to",
                "Receive wallet",
                "fail",
                "X402_PAY_TO_ADDRESS not set",
                'Add X402_PAY_TO_ADDRESS=0xYourWallet to .env',
            )
        )

    if settings.evm_private_key:
        checks.append(
            _check(
                "buyer_key",
                "Vault key (optional)",
                "pass",
                "EVM_PRIVATE_KEY configured for pay_and_fetch",
            )
        )
    else:
        checks.append(
            _check(
                "buyer_key",
                "Vault key (optional)",
                "warn",
                "EVM_PRIVATE_KEY not set — paying disabled",
                "Optional: set EVM_PRIVATE_KEY for testnet pay_and_fetch",
            )
        )

    # Probe the LIVE quota store object, not the env var: REDIS_URL being set
    # proves nothing if startup fell back to memory.
    store = commerce.quota_store
    redis_mode = getattr(store, "mode", "memory")
    if redis_mode == "redis":
        try:
            store.ping()
            checks.append(
                _check(
                    "redis",
                    "Persistence",
                    "pass",
                    "Redis quota store active (live PING ok)",
                )
            )
        except Exception as exc:
            checks.append(
                _check(
                    "redis",
                    "Persistence",
                    "fail",
                    f"Redis quota store lost its connection: {exc}",
                    "Restore Redis availability, then restart the server",
                )
            )
    elif settings.redis_url:
        reason = getattr(store, "fallback_reason", None) or "unreachable at startup"
        checks.append(
            _check(
                "redis",
                "Persistence",
                "fail",
                f"REDIS_URL set but running IN-MEMORY ({reason}) — "
                "paid entitlements will not survive a restart",
                "Verify REDIS_URL and Redis availability, then restart",
            )
        )
    else:
        checks.append(
            _check(
                "redis",
                "Persistence",
                "warn",
                "In-memory quota store — resets on restart",
                "Set REDIS_URL before selling to real buyers",
            )
        )

    # The ledgers are the only local record that a sale happened; on an
    # ephemeral host a file-backed ledger is lost on the next restart.
    if ledger_store.ledger_store is not None:
        try:
            ledger_store.ledger_store.ping()
            checks.append(
                _check(
                    "ledger",
                    "Ledger persistence",
                    "pass",
                    "Redis ledger active (settled spend/revenue survive a restart)",
                )
            )
        except Exception as exc:
            checks.append(
                _check(
                    "ledger",
                    "Ledger persistence",
                    "fail",
                    f"Redis ledger lost its connection: {exc}",
                    "Restore Redis availability, then restart the server",
                )
            )
    elif settings.redis_url:
        reason = redis_client.fallback_reason or "unreachable at startup"
        checks.append(
            _check(
                "ledger",
                "Ledger persistence",
                "fail",
                f"REDIS_URL set but the ledgers fell back to FILES ({reason}) — "
                "settled sales will be lost on the next restart",
                "Verify REDIS_URL and Redis availability, then restart",
            )
        )
    else:
        checks.append(
            _check(
                "ledger",
                "Ledger persistence",
                "warn",
                "File-backed ledgers — lost on restart if the host has no disk",
                "Set REDIS_URL on any host without persistent storage",
            )
        )

    # The registry holds what each product has actually earned; file-backed, a
    # restart resets a sold product's revenue to zero while the money is real.
    if swarm_registry.snapshot is not None:
        checks.append(
            _check(
                "registry",
                "Listing persistence",
                "pass",
                f"Swarm registry persisted to {swarm_registry.snapshot}",
            )
        )
    elif settings.redis_url:
        reason = redis_client.fallback_reason or "unreachable at startup"
        checks.append(
            _check(
                "registry",
                "Listing persistence",
                "fail",
                f"REDIS_URL set but the swarm registry fell back to FILES ({reason})"
                " — listings and per-product revenue reset on the next restart",
                "Verify REDIS_URL and Redis availability, then restart",
            )
        )
    elif swarm_registry.persist_path is not None:
        checks.append(
            _check(
                "registry",
                "Listing persistence",
                "warn",
                "Swarm registry in a local file — lost on restart if the host "
                "has no disk",
                "Set REDIS_URL on any host without persistent storage",
            )
        )
    else:
        checks.append(
            _check(
                "registry",
                "Listing persistence",
                "warn",
                "Swarm registry persistence disabled — listings die on restart",
                "Unset SWARM_PRODUCTS_FILE or set REDIS_URL",
            )
        )

    ok, detail = _ping_url(f"{settings.x402_facilitator_url.rstrip('/')}/supported")
    checks.append(
        _check(
            "facilitator",
            "Facilitator reachable",
            "pass" if ok else "fail",
            detail,
            None if ok else f"Check X402_FACILITATOR_URL={settings.x402_facilitator_url}",
        )
    )

    ok, detail = _ping_url(settings.cdp_discovery_url)
    checks.append(
        _check(
            "discovery",
            "CDP discovery reachable",
            "pass" if ok else "warn",
            detail,
            None if ok else "Discovery may require auth in production",
        )
    )

    mcp_servers = _read_mcp_server_keys()
    agent_prefixes = _agent_tool_prefixes()
    if mcp_servers and agent_prefixes:
        server_keys = set(mcp_servers.keys())
        missing = sorted(agent_prefixes - server_keys)
        if missing:
            checks.append(
                _check(
                    "mcp_json",
                    "MCP server keys",
                    "fail",
                    f"Agent tools reference missing servers: {', '.join(missing)}",
                    f"Add keys to .mcp.json: {', '.join(missing)}",
                )
            )
        else:
            checks.append(
                _check(
                    "mcp_json",
                    "MCP server keys",
                    "pass",
                    f"All agent prefixes covered: {', '.join(sorted(agent_prefixes))}",
                )
            )
    else:
        checks.append(
            _check(
                "mcp_json",
                "MCP server keys",
                "skip",
                "No .mcp.json or agent files to validate",
            )
        )

    checks.append(
        _check(
            "network",
            "Default network",
            "pass",
            settings.x402_default_network,
        )
    )

    # Revenue-network coherence: a public deploy that collects payments must
    # not serve testnet revenue challenges — free Sepolia USDC would buy real
    # pro quota / tool credits.
    from app.x402_services import resolve_revenue_network

    revenue_net = resolve_revenue_network()
    testnets = {"eip155:84532"}
    base = settings.public_base_url.lower()
    is_local = base.startswith(("http://localhost", "http://127.", "http://[::1]"))
    if settings.x402_pay_to_address and not is_local and revenue_net in testnets:
        checks.append(
            _check(
                "revenue_network",
                "Revenue network",
                "fail",
                f"Public deploy would sell pro tier/credits on testnet {revenue_net}",
                "Set REVENUE_NETWORK=eip155:8453 (or configure CDP creds)",
            )
        )
    else:
        checks.append(
            _check(
                "revenue_network",
                "Revenue network",
                "pass",
                revenue_net,
            )
        )

    # RPC Health & Failover
    rpc_ok, rpc_msg = _ping_rpc(settings.base_rpc_url)
    if rpc_ok:
        checks.append(_check("rpc", "Base RPC", "pass", f"RPC healthy: {settings.base_rpc_url}"))
    else:
        # Attempt failover
        fallback_url = "https://base.llamarpc.com"
        if settings.base_rpc_url == fallback_url:
            checks.append(_check("rpc", "Base RPC", "fail", f"Fallback RPC failed: {rpc_msg}", "Check network connection"))
        else:
            fb_ok, fb_msg = _ping_rpc(fallback_url)
            if fb_ok:
                old_url = settings.base_rpc_url
                settings.base_rpc_url = fallback_url
                checks.append(_check("rpc", "Base RPC", "warn", f"RPC failover triggered ({old_url} failed). Swapped to {fallback_url}", "Investigate primary RPC outage"))
            else:
                checks.append(_check("rpc", "Base RPC", "fail", "Both primary and fallback RPC failed", "Check network connection"))

    # MailRail Messaging & Receipt Rail
    if settings.mailrail_enabled:
        provider = settings.mailrail_provider.lower()
        if provider == "resend":
            if settings.mailrail_api_key and settings.mailrail_api_key.startswith("re_"):
                checks.append(_check("mailrail", "MailRail provider", "pass", f"Resend API active (from: {settings.mailrail_from_address})"))
            else:
                checks.append(_check("mailrail", "MailRail provider", "fail", "Resend selected but MAILRAIL_API_KEY missing or invalid", "Set MAILRAIL_API_KEY=re_..."))
        elif provider == "webhook":
            if settings.mailrail_webhook_url and settings.mailrail_webhook_url.startswith("http"):
                checks.append(_check("mailrail", "MailRail provider", "pass", f"Webhook active (URL: {settings.mailrail_webhook_url[:30]}...)"))
            else:
                checks.append(_check("mailrail", "MailRail provider", "fail", "Webhook selected but MAILRAIL_WEBHOOK_URL missing or invalid", "Set MAILRAIL_WEBHOOK_URL=https://..."))
        elif provider == "smtp":
            if settings.mailrail_smtp_url and settings.mailrail_smtp_url.startswith(("smtp://", "smtps://")):
                checks.append(_check("mailrail", "MailRail provider", "pass", f"SMTP active (from: {settings.mailrail_from_address})"))
            else:
                checks.append(_check("mailrail", "MailRail provider", "fail", "SMTP selected but MAILRAIL_SMTP_URL missing or invalid", "Set MAILRAIL_SMTP_URL=smtps://..."))
        else:
            checks.append(_check("mailrail", "MailRail provider", "pass", "Hermetic file ledger active (ledger/mailrail.jsonl)"))
    else:
        checks.append(_check("mailrail", "MailRail provider", "pass", "MailRail disabled (offline mock fallback active)"))

    failed = sum(1 for c in checks if c["status"] == "fail")
    warned = sum(1 for c in checks if c["status"] == "warn")

    return {
        "checks": checks,
        "summary": {
            "pass": sum(1 for c in checks if c["status"] == "pass"),
            "fail": failed,
            "warn": warned,
            "ready": failed == 0,
        },
        "config": {
            "has_pay_to": bool(settings.x402_pay_to_address),
            "has_buyer_key": bool(settings.evm_private_key),
            "redis_mode": redis_mode,
            "network": settings.x402_default_network,
        },
    }


def format_cli_report(report: dict[str, Any]) -> str:
    lines = ["x402 Mission Control — Doctor", ""]
    for check in report["checks"]:
        status = check["status"].upper()
        lines.append(f"[{status}] {check['name']}: {check['message']}")
        if check.get("fix") and check["status"] in ("fail", "warn"):
            lines.append(f"       fix: {check['fix']}")
    summary = report["summary"]
    lines.append("")
    lines.append(
        f"Summary: {summary['pass']} pass, {summary['warn']} warn, {summary['fail']} fail"
    )
    return "\n".join(lines)


def main() -> int:
    report = run_checks()
    print(format_cli_report(report))
    return 0 if report["summary"]["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())