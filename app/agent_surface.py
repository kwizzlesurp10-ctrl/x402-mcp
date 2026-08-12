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


def ownership_proofs() -> list[str]:
    """Signatures proving the operator controls this origin, if any exist.

    A directory will list a URL anyone submits; an ownership proof is what
    distinguishes the operator's listing from a stranger's. Producing one
    requires the receive wallet's key, so this stays empty until the operator
    sets it — the deployment simply advertises without the proof until then.
    """
    return [p.strip() for p in settings.ownership_proofs.split(",") if p.strip()]


def _us_city_paid_resources(base: str) -> list[dict[str, Any]]:
    """US multi-city network resources (includes MN network path + samples)."""
    try:
        from app.city_compliance import registry
    except Exception:  # pragma: no cover — import guard during partial deploys
        return []

    out: list[dict[str, Any]] = []
    for entry in registry.list_cities():
        code = entry["code"]
        out.append(
            {
                "url": f"{base}/us/{code}/property-check/sample",
                "method": "GET",
                "price": "free",
                "network": None,
                "name": f"{entry['name']} compliance (free sample)",
                "what": (
                    f"Free fixed-address sample for {entry['name']}, {entry['state']}. "
                    f"Sample address: {entry['sample_address']}. "
                    f"Paid: {base}/us/{code}/property-check."
                ),
                "params": {},
            }
        )
        out.append(
            {
                "url": f"{base}/us/{code}/property-check",
                "method": "GET",
                "price": entry["price"],
                "network": settings.x402_default_network,
                "name": entry["service_name"],
                "what": (
                    f"{entry['sources_label']}. "
                    f"$0.01-class USDC on Base. Free sample: "
                    f"{base}/us/{code}/property-check/sample. "
                    f"Catalog: {base}/us/cities."
                ),
                "params": {"address": "street address string, 1-120 chars (required)"},
            }
        )
    return out


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
            "url": f"{base}/mn/property-check/sample",
            "method": "GET",
            "price": "free",
            "network": None,
            "name": "Minneapolis rental compliance (free sample)",
            "what": "Free fixed-address sample of the paid MN join: live "
            "compliance_verdict + license / violation / condemned fields for "
            "1700 Penn Ave N. Any other address requires payment at "
            f"{base}/mn/property-check.",
            "params": {},
        },
        {
            "url": f"{base}/mn/property-check",
            "method": "GET",
            "price": settings.mn_property_check_price,
            "network": settings.x402_default_network,
            "name": "Minneapolis rental compliance",
            "what": "One-call compliance_verdict (licensed_clean | "
            "licensed_with_violations | unlicensed | condemned_or_boarded) plus "
            "rental license status, violation history, and condemned/boarded "
            "flag for a Minneapolis street address, from city open data. "
            f"Free sample (fixed address): {base}/mn/property-check/sample.",
            "params": {"address": "street address string, 1-120 chars (required)"},
        },
        {
            "url": f"{base}/us/cities",
            "method": "GET",
            "price": "free",
            "network": None,
            "name": "US City Open-Data Compliance Network (catalog)",
            "what": "Free machine catalog of multi-city property compliance "
            "endpoints (14 jurisdictions: mn, sea, nyc, chi, den, sf, lax, "
            "bos, phi, orl, nola, moco, gain, kc): paid URLs, sample URLs, "
            "price, and open-data sources.",
            "params": {},
        },
        *_us_city_paid_resources(base),
        {
            "url": f"{base}/base/finality-check",
            "method": "GET",
            "price": settings.finality_check_price,
            "network": settings.x402_default_network,
            "name": "Base transaction finality check",
            "what": "Classify a Base mainnet tx hash as not_found, pending, "
            "unsafe (sequencer-confirmed only), safe (L1-attested), or "
            "finalized (L1-finalized) -- read from the node's own safe/"
            "finalized block tags, not a modeled probability. Call after "
            "submitting a tx, when tx-decision answers the question before.",
            "params": {"tx": "0x-prefixed 32-byte transaction hash (required)"},
        },
    ]


def well_known_x402() -> dict[str, Any]:
    """Machine manifest of the paid surface, content from live config.

    `version` + `resources` as bare URL strings is x402scan's published
    fan-out schema, and this document was serving neither: `x402_version`
    under a different key, and `resources` as an array of objects their
    parser cannot read. The richer per-resource detail we already had moves
    to `resource_details` rather than being dropped — a compat document that
    parses is worth more than a bespoke one that doesn't, and `/openapi.json`
    (which crawlers read first) carries the same prices either way.
    """
    return {
        "version": 1,
        "x402_version": 2,
        "service": "x402-micropayments-mcp",
        "base_url": _base(),
        "networks": [settings.x402_default_network],
        "payment_header": "PAYMENT-SIGNATURE",
        "challenge_header": "PAYMENT-REQUIRED",
        "receipt_header": "PAYMENT-RESPONSE",
        "resources": [r["url"] for r in paid_resources() if r["price"] != "free"],
        "resource_details": paid_resources(),
        # Omitted entirely rather than sent empty: an empty proofs array reads
        # as a failed proof, absence reads as "not claimed yet".
        **({"ownershipProofs": ownership_proofs()} if ownership_proofs() else {}),
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
        "## Canonical Visit / Resource URLs",
        "",
        "Use these absolute storefront URLs for Gold402, 24K Labs, Bazaar, and",
        "agent directories. Do **not** use Mission Control SPA hosts",
        "(`*.vercel.app` mission-control) as Resource URLs — they serve the",
        "React shell only and do not proxy payment-gated paths.",
        "",
        f"- Catalog: {base}/us/cities",
        f"- Paid example: {base}/us/sea/property-check",
        f"- Free sample: {base}/us/sea/property-check/sample",
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
        "- **finality-check is gated by the x402 SDK's own middleware, not this",
        "  repo's hand-rolled path**: a malformed `tx` still returns 402 (not",
        "  422) if unpaid, since payment gating runs before query validation;",
        "  paid-but-malformed still safely fails closed (no settlement) but as a",
        "  422 after verification, not before it. Its revenue is mirrored into",
        "  this repo's ledger/dashboard on the same terms as every other product",
        "  -- recorded only after settlement actually succeeds.",
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
