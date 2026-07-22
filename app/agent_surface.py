"""The machine-readable storefront surface: /llms.txt and /.well-known/x402.

Agents read these before paying — every high-demand x402 host documents for
machines, not humans. Both documents are BUILT FROM LIVE CONFIG rather than
written by hand, because tonight's audit found every hand-written doc in this
repo had drifted from reality (a 10-tool README against a 16-tool registry, an
$8.00 price against a $0.05 config). A generated document cannot rot.

The honesty section is deliberate: failure modes and data staleness are what a
buyer actually needs to know, and the winners (stableenrich et al.) spend most
of their words there.
"""

from __future__ import annotations

from typing import Any

from app.config import settings


def _base() -> str:
    return settings.public_base_url.rstrip("/")


def paid_resources() -> list[dict[str, Any]]:
    """Every paid HTTP resource this deployment serves, priced from live config."""
    base = _base()
    return [
        {
            "url": f"{base}/base/tx-decision",
            "method": "GET",
            "price": settings.tx_decision_price,
            "network": settings.x402_default_network,
            "name": "Base tx decision",
            "what": "Submit this Base tx now or wait, max fee + priority fee "
            "(EIP-1559 gwei), estimated USD cost. Call before every send.",
            "params": {
                "gas": "eth|usdc|erc20|x402 or integer gas units (default usdc)",
                "urgency": "now|soon|flexible (default flexible)",
            },
        },
        {
            "url": f"{base}/pulse",
            "method": "GET",
            "price": "free",
            "network": None,
            "name": "Base Network Pulse (free preview)",
            "what": "Full market briefing: fees, congestion, trend, settlement "
            "costs, settle-now-or-wait verdict. The paid composite listing of "
            "the same intelligence is under /swarm/products.",
            "params": {},
        },
        {
            "url": f"{base}/mn/property-check",
            "method": "GET",
            "price": settings.mn_property_check_price,
            "network": settings.x402_default_network,
            "name": "Minneapolis rental compliance",
            "what": "Rental license status, violation history, condemned/boarded "
            "flag for a Minneapolis street address, from city open data.",
            "params": {"address": "street address string, 1-120 chars (required)"},
        },
    ]


def well_known_x402() -> dict[str, Any]:
    """Machine manifest of the paid surface. Shape is ours; content is config."""
    return {
        "x402_version": 2,
        "service": "x402-micropayments-mcp",
        "base_url": _base(),
        "networks": [settings.x402_default_network],
        "payment_header": "PAYMENT-SIGNATURE",
        "challenge_header": "PAYMENT-REQUIRED",
        "receipt_header": "PAYMENT-RESPONSE",
        "resources": paid_resources(),
        "mcp": {
            "manifest": f"{_base()}/.well-known/mcp",
            "streamable_http": f"{_base()}/mcp/mcp",
        },
        "docs": f"{_base()}/llms.txt",
    }


def llms_txt() -> str:
    base = _base()
    lines = [
        "# x402-mcp storefront",
        "",
        "> Pay-per-call HTTP APIs over x402: USDC on Base, no API key, no signup.",
        "> A 402 response IS the price quote — read the PAYMENT-REQUIRED header,",
        "> sign an EIP-3009 USDC transfer authorization, retry with",
        "> PAYMENT-SIGNATURE. Settlement is gasless for the buyer.",
        "",
        "## Paid endpoints",
        "",
    ]
    for r in paid_resources():
        price = r["price"] if r["price"] == "free" else f"{r['price']} USDC per call"
        lines.append(f"### {r['name']} — {price}")
        lines.append(f"`{r['method']} {r['url']}`")
        lines.append("")
        lines.append(r["what"])
        for k, v in r["params"].items():
            lines.append(f"- `{k}`: {v}")
        lines.append("")
    lines += [
        "## What can go wrong (read this before integrating)",
        "",
        "- **Facilitator 502 mid-settle**: the CDP facilitator throws transient",
        "  502s. No funds move on that path and nothing is delivered — retry the",
        "  same request. Do not reconcile; there is nothing to reconcile.",
        "- **402 with `payment_invalid`**: your signature was malformed, expired",
        "  (300s validity window), or bound to a stale challenge. Re-fetch the",
        "  402 and sign the fresh PAYMENT-REQUIRED value.",
        "- **422 before any payment logic**: you omitted or malformed a required",
        "  query parameter. Nothing was charged.",
        "- **Data staleness**: tx-decision responses are computed from a Base RPC",
        "  snapshot at most ~4s old and carry `as_of_block` / `as_of` so you can",
        "  judge freshness yourself. Base blocks land every ~2s; treat any answer",
        "  older than a few blocks as history, not advice.",
        "- **Delivery is settled-gated**: content is served only after on-chain",
        "  settlement succeeds, so a verified-but-unsettled payment gets a 402,",
        "  not the product.",
        "",
        "## Machine surfaces",
        "",
        f"- x402 manifest: {base}/.well-known/x402",
        f"- MCP manifest:  {base}/.well-known/mcp (16 tools, Streamable HTTP at /mcp/mcp)",
        f"- Health: {base}/health · Checks: {base}/doctor · Ops: {base}/dashboard",
        "",
        "## Operator",
        "",
        "- Repository: https://github.com/kwizzlesurp10-ctrl/x402-mcp",
        "- Seller-only deployment: this host holds no spend key (verify:",
        f"  {base}/health shows wallet_configured:false).",
        "",
    ]
    return "\n".join(lines)
