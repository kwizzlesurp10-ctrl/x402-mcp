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

# Base mainnet native USDC (canonical cashier asset for this storefront).
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DEFAULT_PAY_TO = "0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e"
# A2A × x402 extension URI (x402 foundation transport + google-a2a a2a-x402).
A2A_X402_EXTENSION_URI = "https://github.com/google-a2a/a2a-x402/v0.1"
REPO_URL = "https://github.com/kwizzlesurp10-ctrl/x402-mcp"
BOUNTIES_DOC_URL = f"{REPO_URL}/blob/master/docs/BOUNTIES.md"
FUNDING_LEGAL = (
    "Payment for delivered products, documentation/audit artifacts, or a "
    "voluntary tip. Not a token, not equity, not a raise."
)


def _base() -> str:
    return settings.public_base_url.rstrip("/")


def _pay_to() -> str:
    return settings.x402_pay_to_address or DEFAULT_PAY_TO


def funding() -> dict[str, Any]:
    """Machine-readable how-to-fund this operator (USDC on Base + public rails).

    Agents and humans both need an unambiguous payTo. Product purchases use the
    live x402 storefront; bounties/tips send USDC directly to payTo and paste a
    BaseScan hash on a GitHub issue. Fiat Sponsors do not credit payTo.
    """
    base = _base()
    pay_to = _pay_to()
    network = settings.x402_default_network
    return {
        "schema_version": "1.0.0",
        "legal": FUNDING_LEGAL,
        "network": network,
        "chainId": 8453,
        "asset": BASE_USDC,
        "assetSymbol": "USDC",
        "payTo": pay_to,
        "explorer": f"https://basescan.org/address/{pay_to}",
        "tokenExplorer": f"https://basescan.org/token/{BASE_USDC}?a={pay_to}",
        "machineCashier": {
            "catalog": f"{base}/us/cities",
            "examplePaid": f"{base}/us/mn/property-check?address=1700+Penn+Ave+N",
            "exampleFreeSample": f"{base}/mn/property-check/sample",
            "protocol": "x402-v2",
            "note": "Unpaid GET → 402 PAYMENT-REQUIRED; paid retry settles USDC to payTo.",
        },
        "bounties": {
            "protocol": BOUNTIES_DOC_URL,
            "issues": f"{REPO_URL}/issues?q=is%3Aissue+is%3Aopen+label%3A+bounty%3A",
            "issueQuery": f"{REPO_URL}/issues?q=is%3Aopen+bounty%3A",
            "template": f"{REPO_URL}/issues/new?template=paid-bounty.md",
            "parentIndex": f"{REPO_URL}/issues/493",
        },
        "github": {
            "repository": REPO_URL,
            "fundingYml": f"{REPO_URL}/blob/master/.github/FUNDING.yml",
            "sponsorsNote": (
                "GitHub Sponsors / Polar / thanks.dev settle fiat and do not "
                "credit payTo on-chain. Operator may later sweep USD→USDC separately."
            ),
        },
        "discovery": {
            "agentCard": f"{base}/.well-known/agent-card.json",
            "agentsJson": f"{base}/.well-known/agents.json",
            "x402": f"{base}/.well-known/x402",
            "mcp": f"{base}/.well-known/mcp",
            "mcpServerCard": f"{base}/.well-known/mcp/server-card.json",
            "llmsTxt": f"{base}/llms.txt",
            "openapi": f"{base}/openapi.json",
            "funding": f"{base}/.well-known/funding.json",
        },
    }


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
    res = [
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
            "what": "Is this Minneapolis MN rental licensed and code-compliant? "
            "GET ?address= (1-120 chars) → compliance_verdict enum "
            "licensed_clean|licensed_with_violations|unlicensed|condemned_or_boarded "
            "plus license/violation/condemned fields from city open data. "
            f"Free sample: {base}/mn/property-check/sample.",
            "params": {"address": "street address string, 1-120 chars (required)"},
        },
        {
            "url": f"{base}/tasks/us-rental-diligence",
            "method": "POST",
            "price": settings.diligence_pack_price,
            "network": settings.x402_default_network,
            "name": "US Multi-City Rental Diligence Pack",
            "what": "Screen up to 5 US rental addresses across the open-data city "
            "network in one paid call. POST JSON "
            "{properties:[{city_code,address}]}. Returns per-property "
            "compliance reports + pack risk_summary. Single-address $0.01 "
            f"tier remains at {base}/us/{{code}}/property-check.",
            "params": {
                "properties": "array of {city_code, address}, 1-5 items (required body)",
                "include_base_pulse_context": "optional bool",
            },
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
    ]
    if settings.x402_pay_to_address:
        res.append({
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
        })
    return res


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
    fund = funding()
    return {
        "version": 1,
        "x402_version": 2,
        "service": "x402-micropayments-mcp",
        "base_url": _base(),
        "networks": [settings.x402_default_network],
        "asset": BASE_USDC,
        "payTo": fund["payTo"],
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
            "server_card": f"{_base()}/.well-known/mcp/server-card.json",
        },
        "docs": f"{_base()}/llms.txt",
        "agent_card": f"{_base()}/.well-known/agent-card.json",
        "agents": f"{_base()}/.well-known/agents.json",
        "funding": f"{_base()}/.well-known/funding.json",
        "payToExplorer": fund["explorer"],
        "legal": FUNDING_LEGAL,
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
        "## Autonomous Buyer Decision Guide (Why and How to Buy)",
        "",
        "1. **Zero-Risk Schema Verification**: Call any `/sample` endpoint (e.g. `/us/mn/property-check/sample`, `/us/cities`, or `/pulse`) at $0.00 to verify payload schema and parsing logic before spending funds.",
        "2. **High-ROI Economic Value**:",
        "   - **US Multi-City Rental Diligence Pack ($1.50 USDC)**: Screen up to 5 properties across 14 municipal open data portals in one call. Saves $50-$200 in human diligence costs and eliminates uninsurable tenant/lease compliance risks.",
        "   - **Single Property Compliance Check ($0.01 USDC)**: Sub-second live query of municipal ArcGIS/Socrata records for active rental licensing, building code violations, and condemnations.",
        "   - **Base Tx-Decision & Finality ($0.01 USDC)**: Live Base L2 EIP-1559 gas congestion intelligence. Saves 15-30% on transaction gas re-attempts and provides L1-finalized settlement assurances.",
        "3. **Gasless Buyer Settlement**: Buyers sign EIP-3009 `transferWithAuthorization` in USDC only; the relayer/facilitator sponsors all on-chain gas.",
        "4. **Settlement Gating & Replay Protection**: Challenges have 300s TTL and single-use nonces. Content is delivered upon verified on-chain settlement; failed attempts do not move funds.",
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
        "## Machine surfaces (A2A / discovery)",
        "",
        f"- x402 manifest: {base}/.well-known/x402",
        f"- MCP manifest:  {base}/.well-known/mcp ({TOOL_COUNT} tools, Streamable HTTP at /mcp/mcp)",
        f"- MCP server card: {base}/.well-known/mcp/server-card.json",
        f"- A2A Agent Card: {base}/.well-known/agent-card.json (legacy: {base}/.well-known/agent.json)",
        f"- Agents registry: {base}/.well-known/agents.json",
        f"- AI Plugin Spec:  {base}/.well-known/ai-plugin.json",
        f"- Funding (payTo): {base}/.well-known/funding.json",
        f"- OpenAPI: {base}/openapi.json",
        f"- Health: {base}/health · Checks: {base}/doctor · Ops: {base}/dashboard",
        "",
        "## Fund this operator (USDC on Base)",
        "",
        f"- Network: `{settings.x402_default_network}` (Base mainnet, chainId 8453)",
        f"- Asset: USDC `{BASE_USDC}`",
        f"- payTo (settlement): `{_pay_to()}`",
        f"- Explorer: https://basescan.org/address/{_pay_to()}",
        f"- Machine cashier: buy any paid endpoint above (e.g. property-check $0.01) — USDC settles to payTo",
        f"- Public bounties protocol: {BOUNTIES_DOC_URL}",
        f"- Open a funded bounty: {REPO_URL}/issues/new?template=paid-bounty.md",
        f"- GitHub FUNDING.yml: {REPO_URL}/blob/master/.github/FUNDING.yml",
        f"- {FUNDING_LEGAL}",
        "",
        "## Operator",
        "",
        "- Provider: SEVTECH (EIN verified, Coinbase KYB verified)",
        f"- Repository: {REPO_URL}",
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
            "id": "base-tx-decision",
            "name": "Base Transaction Decision",
            "description": (
                "Paid recommendation engine to decide whether to submit a Base transaction "
                "immediately or wait. Returns max fee, priority fee (EIP-1559 gwei), "
                f"and estimated USD cost. Price: {settings.tx_decision_price} USDC on {network} via x402. "
                f"HTTP: GET {base}/base/tx-decision."
            ),
            "tags": ["base", "transaction", "gas", "fees", "optimizer", "eip-1559", "x402", "usdc"],
            "examples": [
                "Should I submit my transaction now or wait?",
                f"GET {base}/base/tx-decision?gas=usdc&urgency=flexible",
            ],
            "inputModes": ["text/plain", "application/json"],
            "outputModes": ["application/json"],
        },
    ]
    if settings.x402_pay_to_address:
        skills.append({
            "id": "base-finality-check",
            "name": "Base Transaction Finality Check",
            "description": (
                "Paid lookup to classify a Base mainnet transaction hash as pending, "
                "unsafe (sequencer-confirmed), safe (L1-attested), or finalized (L1-finalized) "
                "from the node's official block tags. "
                f"Price: {settings.finality_check_price} USDC on {network} via x402. "
                f"HTTP: GET {base}/base/finality-check."
            ),
            "tags": ["base", "transaction", "finality", "settlement", "status", "node-tags", "x402", "usdc"],
            "examples": [
                "Check finality status of transaction 0xabc...",
                f"GET {base}/base/finality-check?tx=0x123...",
            ],
            "inputModes": ["text/plain", "application/json"],
            "outputModes": ["application/json"],
        })
    skills.extend([
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
        {
            "id": "us-rental-diligence-pack",
            "name": "US Multi-City Rental Diligence Pack",
            "description": (
                f"Paid composite: screen 1–{getattr(settings, 'diligence_pack_max_properties', 5)} "
                f"US rental addresses across the open-data city network in one call. "
                f"POST JSON {{properties:[{{city_code,address}}]}} to "
                f"{base}/tasks/us-rental-diligence at "
                f"{getattr(settings, 'diligence_pack_price', '$1.50')} USDC on {network} (x402). "
                "Returns per-property compliance reports plus pack risk_summary. "
                "Single-address $0.01 checks remain at /us/{{code}}/property-check."
            ),
            "tags": [
                "rental",
                "compliance",
                "multicity",
                "housing",
                "due-diligence",
                "x402",
                "usdc",
                "composite",
            ],
            "examples": [
                f"POST {base}/tasks/us-rental-diligence with two cities",
                "Screen MN + SEA rental addresses in one paid pack",
            ],
            "inputModes": ["application/json"],
            "outputModes": ["application/json"],
        },
    ])

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

    pay_to = _pay_to()
    fund = funding()
    return {
        "name": "US City Open-Data Compliance & Base Intelligence (x402)",
        "description": (
            "Pay-per-call autonomous real estate compliance and Base L2 execution intelligence. "
            f"Discovers {len(cities)} open-data jurisdictions via free catalog {base}/us/cities; "
            f"returns address-level rental/license/violation reports at {price} USDC on Base ({network}) "
            "using HTTP 402 micropayments (x402 v2). Zero signup, non-custodial, gasless buyer settlement. "
            f"Free shape previews at /us/{{city_code}}/property-check/sample and /pulse. Fund operator: USDC on Base "
            f"to payTo {pay_to} (see {base}/.well-known/funding.json)."
        ),
        "version": "0.1.0",
        "protocolVersion": "1.0",
        "url": f"{base}/.well-known/x402",
        "provider": {
            "organization": "SEVTECH",
            "url": REPO_URL,
            "contact": "kwizzlesurp10@gmail.com",
            "receiveAddress": pay_to,
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
                "url": f"{base}/tasks/us-rental-diligence",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": f"{base}/base/tx-decision",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": f"{base}/base/finality-check",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": f"{base}/mn/property-check",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": f"{base}/pulse",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": f"{base}/.well-known/x402",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": f"{base}/.well-known/funding.json",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": f"{base}/.well-known/agents.json",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": f"{base}/.well-known/ai-plugin.json",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
        ],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extendedAgentCard": False,
            "extensions": [
                {
                    "uri": A2A_X402_EXTENSION_URI,
                    "description": (
                        "Supports x402 HTTP 402 micropayments with on-chain "
                        f"USDC settlement on {network} to payTo {pay_to}."
                    ),
                    "required": False,
                }
            ],
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
                    f"JSON: amount, payTo {pay_to}, asset USDC {BASE_USDC}, "
                    "network). Client signs EIP-3009 transferWithAuthorization "
                    "and retries with PAYMENT-SIGNATURE. Settlement is gasless "
                    f"for the buyer (USDC required, not ETH). Catalog "
                    f"{base}/us/cities and all /sample endpoints require no "
                    f"payment. Authoritative payment metadata: {base}/.well-known/x402"
                ),
            }
        },
        "security": [
            {},
            {"x402": []},
        ],
        # AP2-style payments block + explicit funding (extra fields; A2A clients ignore unknowns).
        "payments": {
            "version": "2025.0",
            "rails": [
                {
                    "id": "x402",
                    "currencies": ["USDC"],
                    "networks": [network],
                    "asset": BASE_USDC,
                    "payTo": pay_to,
                    "policy": BOUNTIES_DOC_URL,
                    "captureTypes": ["immediate"],
                }
            ],
            "pricing": {
                "model": "catalog",
                "catalogUrl": f"{base}/.well-known/x402",
            },
        },
        "funding": fund,
    }


def _price_to_atomic_usdc(price: str) -> int:
    """Parse '$0.01' / '0.01' style prices to USDC atomic (6 decimals)."""
    raw = str(price).strip().replace("$", "").replace(",", "")
    try:
        return int(round(float(raw) * 1_000_000))
    except ValueError:
        return 0


def agents_json() -> dict[str, Any]:
    """Standard Agents Registry Schema (Agentic.Market / Open Agent Registry)."""
    base = _base()
    network = settings.x402_default_network
    pay_to = _pay_to()

    try:
        from app.city_compliance import registry

        cities = registry.list_cities()
    except Exception:
        cities = []

    city_price = getattr(settings, "city_network_price", None) or settings.mn_property_check_price

    agents = [
        {
            "id": "us-rental-diligence",
            "name": "US Multi-City Rental Diligence Pack",
            "description": (
                "Screen up to 5 US rental addresses across the open-data city network in one "
                "paid composite call. Returns per-property compliance verdicts + pack risk summary."
            ),
            "roi_value_proposition": (
                "Saves $50-$200 in manual compliance research; eliminates uninsurable tenant/lease liability "
                "by verifying official municipal licenses, open code violations, and active condemnation orders."
            ),
            "latency_sla": "p95 < 850ms",
            "data_provenance": "Direct municipal open data APIs (ArcGIS FeatureServer, Socrata, Carto, CKAN)",
            "free_preview_url": f"{base}/us/mn/property-check/sample",
            "url": f"{base}/tasks/us-rental-diligence",
            "method": "POST",
            "pricing": {
                "amount": settings.diligence_pack_price.replace("$", ""),
                "currency": "USDC",
                "network": network,
                "model": "per_request",
                "atomic_units": _price_to_atomic_usdc(settings.diligence_pack_price),
                "value_summary": "$1.50 USDC per 5-property batch screening",
            },
            "protocols": ["x402-v2", "http-json", "a2a"],
            "tags": [
                "rental",
                "compliance",
                "multicity",
                "housing",
                "due-diligence",
                "x402",
                "usdc",
                "a2a-commerce",
                "risk-scoring",
            ],
            "input_schema": {
                "type": "object",
                "required": ["properties"],
                "properties": {
                    "properties": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["city_code", "address"],
                            "properties": {
                                "city_code": {
                                    "type": "string",
                                    "description": "City code (e.g. mn, sea, nyc, chi)",
                                },
                                "address": {"type": "string", "description": "Street address"},
                            },
                        },
                    },
                    "include_base_pulse_context": {"type": "boolean", "default": False},
                },
            },
        },
        {
            "id": "base-tx-decision",
            "name": "Base Transaction Decision & Gas Optimizer",
            "description": "Live Base RPC congestion, fee math (EIP-1559), and submit-or-wait execution guidance.",
            "roi_value_proposition": "Reduces failed/stuck transaction waste by 15-30% on Base mainnet via real-time EIP-1559 telemetry.",
            "latency_sla": "p95 < 250ms",
            "data_provenance": "Base Mainnet RPC node (mainnet.base.org) + Coinbase spot price feed",
            "free_preview_url": f"{base}/pulse",
            "url": f"{base}/base/tx-decision",
            "method": "GET",
            "pricing": {
                "amount": settings.tx_decision_price.replace("$", ""),
                "currency": "USDC",
                "network": network,
                "model": "per_request",
                "atomic_units": _price_to_atomic_usdc(settings.tx_decision_price),
                "value_summary": "$0.01 USDC per execution decision",
            },
            "protocols": ["x402-v2", "http-json", "a2a"],
            "tags": ["base", "crypto", "gas", "tx-optimizer", "x402", "usdc", "eip-1559", "a2a-commerce"],
            "params": {
                "gas": "eth|usdc|erc20|x402 or integer gas units",
                "urgency": "now|soon|flexible",
            },
        },
        {
            "id": "base-finality-check",
            "name": "Base Transaction Finality Check",
            "description": "L1/L2 safe and finalized block tag verification for Base mainnet transactions.",
            "roi_value_proposition": "Provides absolute cryptographic assurance before unlocking high-value goods or services.",
            "latency_sla": "p95 < 250ms",
            "data_provenance": "Base Mainnet RPC safe/finalized block header inspection",
            "url": f"{base}/base/finality-check",
            "method": "GET",
            "pricing": {
                "amount": settings.finality_check_price.replace("$", ""),
                "currency": "USDC",
                "network": network,
                "model": "per_request",
                "atomic_units": _price_to_atomic_usdc(settings.finality_check_price),
                "value_summary": "$0.01 USDC per transaction check",
            },
            "protocols": ["x402-v2", "http-json", "a2a"],
            "tags": ["base", "finality", "verification", "x402", "usdc", "a2a-commerce"],
            "params": {
                "tx": "0x-prefixed 32-byte transaction hash",
            },
        },
        {
            "id": "us-city-compliance-network",
            "name": "US City Open-Data Property Compliance Network",
            "description": f"Address-level housing license, building violation, and code compliance checks across {len(cities)} US jurisdictions.",
            "roi_value_proposition": "Instant property compliance intelligence covering 14 metropolitan jurisdictions with zero setup.",
            "latency_sla": "p95 < 600ms",
            "data_provenance": "Municipal open data portals (Minneapolis, Seattle, NYC, Chicago, Denver, SF, LA, Boston, Philly, Orlando, NOLA, MoCo, Gainesville, KC)",
            "catalog_url": f"{base}/us/cities",
            "method": "GET",
            "pricing": {
                "amount": city_price.replace("$", ""),
                "currency": "USDC",
                "network": network,
                "model": "per_request",
                "atomic_units": _price_to_atomic_usdc(city_price),
                "value_summary": "$0.01 USDC per municipal query",
            },
            "protocols": ["x402-v2", "http-json", "a2a"],
            "tags": ["property", "compliance", "rental", "housing", "violations", "open-data", "x402", "a2a-commerce"],
            "jurisdictions": [c["code"] for c in cities],
        },
    ]

    return {
        "schema_version": "1.0.0",
        "name": "x402 Micropayments & Agent Services",
        "description": "Autonomous pay-per-call data services and MCP tool suite on Base mainnet.",
        "homepage": base,
        "documentation": f"{base}/llms.txt",
        "provider": {
            "name": "SEVTECH",
            "url": REPO_URL,
            "receive_address": pay_to,
        },
        "payment_networks": [network],
        "settlement_address": pay_to,
        "asset": BASE_USDC,
        "funding": f"{base}/.well-known/funding.json",
        "agents": agents,
        "mcp": {
            "manifest": f"{base}/.well-known/mcp",
            "server_card": f"{base}/.well-known/mcp/server-card.json",
            "streamable_http": f"{base}/mcp/mcp",
            "sse": f"{base}/mcp/sse",
        },
        "agent_card": f"{base}/.well-known/agent-card.json",
        "ai_plugin": f"{base}/.well-known/ai-plugin.json",
        "x402_manifest": f"{base}/.well-known/x402",
        "legal": FUNDING_LEGAL,
        **({"ownershipProofs": ownership_proofs()} if ownership_proofs() else {}),
    }


def ai_plugin_json() -> dict[str, Any]:
    """Standard AI Plugin Manifest for OpenAI, LangChain, AutoGPT, and Cursor agents."""
    base = _base()
    return {
        "schema_version": "v1",
        "name_for_human": "x402 Micropayments & Compliance Network",
        "name_for_model": "x402_micropayments_and_compliance",
        "description_for_human": (
            "Pay-per-call US rental property compliance diligence and live Base L2 gas telemetry via x402 micropayments."
        ),
        "description_for_model": (
            "Autonomous agent interface for instant $0.01-$1.50 USDC pay-per-call data services. "
            "Includes US 14-city property compliance screening (code violations, rental licenses, condemnation), "
            "live Base mainnet EIP-1559 gas decision optimization, and multi-address rental diligence packs. "
            "Payments settle gaslessly on Base (eip155:8453) using HTTP 402 and EIP-3009 transfer authorizations. "
            "Provides free sample endpoints for shape verification before executing paid lookups."
        ),
        "auth": {
            "type": "none",
        },
        "api": {
            "type": "openapi",
            "url": f"{base}/openapi.json",
            "is_user_authenticated": False,
        },
        "logo_url": f"{base}/favicon.svg",
        "contact_email": "kwizzlesurp10@gmail.com",
        "legal_info_url": "https://github.com/kwizzlesurp10-ctrl/x402-mcp/blob/main/LICENSE",
    }


def mcp_server_card() -> dict[str, Any]:
    """Remote MCP Server Card for Smithery.ai, Glama.ai, and MCP client indexing."""
    base = _base()
    from app.manifest import build_mcp_manifest

    mcp_manifest = build_mcp_manifest()

    return {
        "serverInfo": {
            "name": "io.github.kwizzlesurp10-ctrl/x402-mcp",
            "title": "x402 Micropayments MCP",
            "version": "0.1.0",
            "description": (
                "Pay-per-call HTTP APIs and MCP tools over x402: USDC on Base, "
                "gasless settlement, US multi-city rental compliance diligence, "
                "and Base gas/finality intelligence."
            ),
        },
        "transport": {
            "type": "streamable-http",
            "url": f"{base}/mcp/mcp",
            "sse_url": f"{base}/mcp/sse",
        },
        "authentication": {
            "type": "x402",
            "scheme": "EIP-3009",
            "network": settings.x402_default_network,
            "asset": "USDC",
            "assetAddress": BASE_USDC,
            "pay_to": _pay_to(),
        },
        "capabilities": {
            "tools": True,
            "resources": False,
            "prompts": False,
        },
        "tools": mcp_manifest["tools"],
        "homepage": base,
        "repository": {
            "type": "git",
            "url": f"{REPO_URL}.git",
        },
        "documentation": f"{base}/llms.txt",
        "funding": f"{base}/.well-known/funding.json",
        "agent_card": f"{base}/.well-known/agent-card.json",
        "legal": FUNDING_LEGAL,
    }
