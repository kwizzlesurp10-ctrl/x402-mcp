"""The machine-readable storefront surface: /llms.txt, /.well-known/x402, A2A agent card.

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
from app.tools_registry import TOOL_COUNT


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
        f"- MCP manifest:  {base}/.well-known/mcp ({TOOL_COUNT} tools, Streamable HTTP at /mcp/mcp)",
        f"- A2A Agent Card: {base}/.well-known/agent-card.json",
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


def agent_card() -> dict[str, Any]:
    """A2A Protocol v1.0 Agent Card for ecosystem discovery.

    Built from the live city registry and pricing config so skills cannot
    drift from /us/cities. Advertises HTTP+JSON interfaces only — this host
    is an x402 micropayment storefront, not a JSON-RPC A2A Task endpoint.
    Streaming and push are disabled because they are not implemented.
    """
    base = _base()
    try:
        from app.city_compliance import registry
    except Exception:  # pragma: no cover
        cities: list[dict[str, Any]] = []
    else:
        cities = registry.list_cities()

    codes = [c["code"] for c in cities]
    codes_pipe = "|".join(codes) if codes else "mn"
    # Prefer the network-wide city price when present; fall back to MN price.
    price = getattr(settings, "city_network_price", None) or settings.mn_property_check_price
    network = settings.x402_default_network

    skills: list[dict[str, Any]] = [
        {
            "id": "us-cities-catalog",
            "name": "US City Open-Data Compliance Catalog",
            "description": (
                "Free machine-readable catalog of multi-city US property compliance "
                f"endpoints. Returns network=us-city-open-data-compliance, price, "
                f"CAIP-2 {network}, and per-city paid_url, sample_url, sample_address, "
                "sources_label, and tags. No payment required. "
                f"MCP tool: list_us_cities. HTTP: GET {base}/us/cities."
            ),
            "tags": [
                "catalog",
                "discovery",
                "us-cities",
                "housing",
                "compliance",
                "open-data",
                "x402",
                "free",
            ],
            "examples": [
                "List all US city property compliance endpoints",
                "Which cities support rental compliance checks and at what price?",
                f"GET {base}/us/cities",
            ],
            "inputModes": ["text/plain", "application/json"],
            "outputModes": ["application/json"],
        },
        {
            "id": "us-city-property-check",
            "name": "US City Property Compliance Check",
            "description": (
                f"Paid address-level open-data compliance report for one of "
                f"{len(cities)} US jurisdictions. Input: city code "
                f"({codes_pipe}) and street address (1-120 chars). "
                f"Price: {price} USDC on {network} via x402 "
                "(HTTP 402 + PAYMENT-SIGNATURE). Output: JSON compliance report "
                "from city open data. Free fixed-address samples at "
                "/us/{code}/property-check/sample without payment. "
                "MCP: get_us_city_property_sample then check_us_city_property "
                "(or pay_and_fetch on paid_url)."
            ),
            "tags": [
                "property",
                "compliance",
                "rental",
                "housing",
                "violations",
                "open-data",
                "x402",
                "usdc",
                "base",
            ],
            "examples": [
                f"Check Minneapolis rental license for 1700 Penn Ave N (city=mn)",
                f"GET {base}/us/{{city_code}}/property-check?address={{street}}",
            ],
            "inputModes": ["text/plain", "application/json"],
            "outputModes": ["application/json"],
        },
        {
            "id": "us-city-property-check-sample",
            "name": "US City Property Compliance Sample (Free)",
            "description": (
                "Free fixed-address sample report for any supported city code. "
                "Same JSON shape as the paid property-check; no payment required. "
                "Use for integration testing before paying for arbitrary addresses. "
                "MCP tool: get_us_city_property_sample(city_code)."
            ),
            "tags": [
                "sample",
                "free",
                "property",
                "compliance",
                "open-data",
                "x402",
            ],
            "examples": [
                f"GET {base}/us/mn/property-check/sample",
                f"GET {base}/us/sea/property-check/sample",
                "Show the free Chicago sample compliance report (city=chi)",
            ],
            "inputModes": ["text/plain", "application/json"],
            "outputModes": ["application/json"],
        },
    ]

    for c in cities:
        code = c["code"]
        sample_addr = c["sample_address"]
        paid = c["paid_url"]
        sample = c["sample_url"]
        tags = list(
            dict.fromkeys(
                list(c.get("tags") or [])
                + [code, c["name"].lower().replace(" ", ""), "compliance", "x402"]
            )
        )
        skills.append(
            {
                "id": f"property-check-{code}",
                "name": c["service_name"],
                "description": (
                    f"{c['service_name']} for {c['name']}, {c['state']}. "
                    f"Source: {c['sources_label']}. "
                    f"Paid: GET {paid}?address={{street}} at {c['price']} USDC "
                    f"on {c['network']} (x402). Free sample: {sample} "
                    f"(fixed address: {sample_addr})."
                ),
                "tags": tags,
                "examples": [
                    f"Check {c['name']} compliance for {sample_addr}",
                    f"GET {paid}?address={sample_addr.replace(' ', '%20')}",
                    f"Free sample: GET {sample}",
                ],
                "inputModes": ["text/plain", "application/json"],
                "outputModes": ["application/json"],
            }
        )

    return {
        "name": "US City Open-Data Compliance (x402)",
        "description": (
            "Pay-per-call US multi-city property compliance agent. Discovers "
            f"{len(cities)} open-data jurisdictions via free catalog "
            f"{base}/us/cities; returns address-level rental/license/violation "
            f"reports at {price} USDC on Base ({network}) using HTTP 402 "
            "micropayments (x402 v2). No API key, no signup. Free samples at "
            "/us/{city_code}/property-check/sample."
        ),
        "version": "0.1.0",
        "protocolVersion": "1.0",
        "provider": {
            "organization": "x402-mcp",
            "url": "https://github.com/kwizzlesurp10-ctrl/x402-mcp",
        },
        "documentationUrl": f"{base}/llms.txt",
        "supportedInterfaces": [
            {
                "url": f"{base}/us/cities",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": f"{base}/us/{{city_code}}/property-check",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": f"{base}/.well-known/x402",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
        ],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extendedAgentCard": False,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": skills,
        "securitySchemes": {
            "x402": {
                "type": "apiKey",
                "in": "header",
                "name": "PAYMENT-SIGNATURE",
                "description": (
                    f"x402 v2 micropayment on {network}. Unauthenticated GET "
                    "returns HTTP 402 with PAYMENT-REQUIRED challenge (base64 "
                    "JSON: amount, payTo, asset USDC, network). Client signs "
                    "EIP-3009 transferWithAuthorization and retries with "
                    "PAYMENT-SIGNATURE. Settlement is gasless for the buyer "
                    f"(USDC required, not ETH). Catalog {base}/us/cities and "
                    "all /sample endpoints require no payment. Authoritative "
                    f"payment metadata: {base}/.well-known/x402"
                ),
            }
        },
        "security": [
            {},
            {"x402": []},
        ],
    }
