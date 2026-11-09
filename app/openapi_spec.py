"""The public OpenAPI document — the one discovery crawlers actually read.

x402scan (and the `@agentcash/discovery` auditor it ships) resolves a seller in
strict precedence: `/openapi.json` FIRST, `/.well-known/x402` only as a
fallback. FastAPI generates that document for free, which is exactly the
problem — run their auditor against the untouched spec and you get:

    Source: openapi   Routes: 33
    [info] L2_NO_PAID_ROUTES - No endpoints are marked as paid or apiKey+paid.

So the storefront advertised itself to the largest x402 explorer as a free API
with nothing to sell, and the hand-built `/.well-known/x402` never got read at
all. It also published 33 routes, including `/wallet`, `/ledger/{name}`,
`/security`, `/swarm/run`, `/stripe/webhook` and `/probe` — an operator surface
that has no business in a public discovery document.

This module rewrites the generated schema into the document a buyer needs:

- paid operations carry `x-payment-info` (price + protocol) and a documented
  402 response, priced from `agent_surface.paid_resources()` so the spec cannot
  drift from `/llms.txt` and `/.well-known/x402`;
- everything that is not a product or a machine-readable doc is dropped, by
  ALLOWLIST — a new internal route is invisible by default, which is the safe
  direction for this to fail;
- surviving free routes declare `security: []`, the explicit "public on
  purpose" marker their auditor asks for, so silence is never read as an
  oversight;
- `info.x-guidance` gives an agent the payment flow in one paragraph.

Deliberately NOT cached: the same reason `agent_surface` builds its documents
from live config rather than a checked-in file. A spec regenerated per request
cannot drift from the prices actually being charged.
"""

from __future__ import annotations

from typing import Any

from app import agent_surface
from app.config import settings

# Machine-readable docs and the free preview: public on purpose, and useful to
# an agent deciding whether to pay. Everything not listed here and not a paid
# product is dropped from the public document.
PUBLIC_FREE_PATHS: tuple[str, ...] = (
    "/health",
    "/llms.txt",
    "/.well-known/x402",
    "/.well-known/mcp",
    "/.well-known/mcp/server-card.json",
    "/.well-known/agents.json",
    "/.well-known/agentic-market.json",
    "/.well-known/agent-card.json",
    "/.well-known/agent.json",
    "/.well-known/funding.json",
    "/pulse",
    "/mn/property-check/sample",
    "/us/cities",
    "/us/{city_code}/property-check/sample",
    "/robots.txt",
)

# What a crawler must never learn from us. Not used for filtering (the
# allowlist already excludes them) — this is the list the guard test asserts
# stayed out, so a future refactor of the allowlist cannot quietly re-expose
# the operator surface.
OPERATOR_PATHS: tuple[str, ...] = (
    "/wallet",
    "/ledger/{name}",
    "/security",
    "/swarm/run",
    "/swarm/runs",
    "/swarm/revenue",
    "/swarm/assessment",
    "/pulse/publish",
    "/probe",
    "/seller/requirements",
    "/stripe/checkout",
    "/stripe/webhook",
    "/os",
    "/os/history",
    "/doctor",
    "/demand",
    "/events",
    "/stats",
    "/dashboard",
    "/quota/{agent_id}",
)

GUIDANCE = """\
Pay-per-call HTTP APIs over x402: USDC on Base, no API key, no signup, no \
prior relationship with the seller.

## Paying
A 402 response IS the price quote. Read the PAYMENT-REQUIRED header, sign an \
EIP-3009 USDC transfer authorization for the quoted atomic amount, and retry \
with PAYMENT-SIGNATURE. Settlement is gasless for the buyer — you need USDC on \
Base, not ETH. Content is served only after settlement succeeds.

## Before you integrate
Full failure modes, staleness guarantees and per-endpoint parameters are at \
/llms.txt. Prices in this document are authoritative for the running \
deployment; the live 402 challenge is authoritative over both.\
"""


def _price_amount(price: str | None) -> str | None:
    """`"$0.01"` -> `"0.01"`. Free or unparseable prices return None.

    x402scan wants a decimal USD string here, NOT the token atomic units used
    in the runtime challenge — mixing those up is on their published list of
    common registration failures.
    """
    if not price or price == "free":
        return None
    cleaned = price.strip().lstrip("$").strip()
    try:
        float(cleaned)
    except ValueError:
        return None
    return cleaned


def _path_of(url: str) -> str:
    base = settings.public_base_url.rstrip("/")
    return url[len(base):] if url.startswith(base) else url


def paid_paths() -> dict[str, str]:
    """Public paid HTTP path -> USD price string, from the one source of truth."""
    paths: dict[str, str] = {}
    for resource in agent_surface.paid_resources():
        amount = _price_amount(resource.get("price"))
        if amount:
            paths[_path_of(resource["url"])] = amount

    # The cataloged Pulse listing is a concrete product URL, not a template —
    # a crawler cannot probe `/swarm/products/{product_id}/purchase`. Publish
    # it only when a pinned id is configured, because that is exactly the
    # condition under which the boot-time republish guarantees the URL exists;
    # advertising it otherwise would earn a "expected 402, got 404".
    if settings.pinned_pulse_product_id:
        amount = _price_amount(settings.pulse_price)
        if amount:
            paths[f"/swarm/products/{settings.pinned_pulse_product_id}/purchase"] = amount
    return paths


def _schema_from_example(value: Any) -> dict[str, Any]:
    """Infer a JSON Schema from a response example.

    Derived rather than hand-written so the OpenAPI response schema and the
    Bazaar extension's output schema come from ONE example per product and
    cannot drift — the same reason every other document here is generated.
    """
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if value is None:
        # A null in the example means "sometimes absent", not "always null".
        return {}
    if isinstance(value, list):
        items = _schema_from_example(value[0]) if value else {}
        return {"type": "array", "items": items}
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {k: _schema_from_example(v) for k, v in value.items()},
        }
    return {}


def output_examples() -> dict[str, dict[str, Any]]:
    """Public path -> a real 200 body, from each product's own discovery example.

    Imported lazily: these modules pull in the RPC and compliance stacks, and
    the spec is built per request.
    """
    from app import (
        diligence_pack,
        finality_check,
        mn_compliance,
        policy_check,
        property_due_diligence_agent,
        tx_decision,
    )
    from app.city_compliance import publish, registry as city_registry

    examples: dict[str, dict[str, Any]] = {
        "/base/tx-decision": tx_decision.DISCOVERY_OUTPUT_EXAMPLE,
        "/base/finality-check": finality_check.DISCOVERY_OUTPUT_EXAMPLE,
        "/mn/property-check": publish.prepare_city_report(
            dict(mn_compliance.DISCOVERY_OUTPUT_EXAMPLE),
            spec=city_registry.get_city("mn").SPEC,
            address_fallback=mn_compliance.SAMPLE_ADDRESS,
        ),
        "/tasks/us-rental-diligence": diligence_pack.DISCOVERY_OUTPUT_EXAMPLE,
        "/x402/policy-check": policy_check.DISCOVERY_PAID_OUTPUT_EXAMPLE,
        "/agent/property-due-diligence": (
            property_due_diligence_agent.DISCOVERY_OUTPUT_EXAMPLE
        ),
    }
    if settings.pinned_pulse_product_id:
        pid = settings.pinned_pulse_product_id
        examples[f"/swarm/products/{pid}/purchase"] = {
            "product_id": pid,
            "topic": "Base Network Pulse @ block 49428640",
            "report": "Base mainnet: base fee 0.005 gwei, congestion low ...",
            "payment_settled": True,
        }
    # Concrete per-city paid paths (x402scan matches the exact resource path).
    for code in city_registry.known_codes():
        mod = city_registry.get_city(code)
        examples[f"/us/{code}/property-check"] = publish.discovery_output_example(mod)
    return examples


def _payment_info(amount: str) -> dict[str, Any]:
    return {
        "protocols": [{"x402": {}}],
        "price": {"mode": "fixed", "currency": "USD", "amount": amount},
    }


# The one input every paid route here takes, and for the cataloged purchase URL
# the only one — its product id is baked into the path. An operation with no
# declared inputs is "strict non-invocable" to x402scan and gets skipped rather
# than listed, so declaring the header is what makes the endpoint callable as
# well as visible. It is also the honest answer to "how do I construct this
# call": sign the challenge, put it here.
_PAYMENT_SIGNATURE_PARAM = {
    "name": "PAYMENT-SIGNATURE",
    "in": "header",
    "required": False,
    "description": "Signed x402 payment payload. Omit it to receive the 402 "
    "challenge; sign that challenge and retry with it to be served.",
    "schema": {"type": "string"},
}

X402_SECURITY_SCHEME = {
    "type": "apiKey",
    "in": "header",
    "name": "PAYMENT-SIGNATURE",
    "description": (
        "Signed x402 payment authorization. Omit to receive a 402 and the "
        "PAYMENT-REQUIRED challenge; sign it and retry with this header."
    ),
}

_PAYMENT_REQUIRED_RESPONSE = {
    "description": "Payment required. The PAYMENT-REQUIRED header carries the "
    "x402 challenge: sign it and retry with PAYMENT-SIGNATURE.",
    "headers": {
        "PAYMENT-REQUIRED": {
            "description": "Base64 x402 challenge (accepts[], atomic amounts).",
            "schema": {"type": "string"},
        }
    },
}


def _declare_paid(
    operation: dict[str, Any], amount: str, output_example: dict[str, Any] | None = None
) -> None:
    """Mark one operation payable, callable, and describable, in place."""
    operation["x-payment-info"] = _payment_info(amount)
    operation["security"] = [{"x402": []}]
    responses = operation.setdefault("responses", {})
    responses["402"] = dict(_PAYMENT_REQUIRED_RESPONSE)

    parameters = operation.setdefault("parameters", [])
    if not any(p.get("name") == "PAYMENT-SIGNATURE" for p in parameters):
        parameters.append(dict(_PAYMENT_SIGNATURE_PARAM))

    # The handlers return bare JSONResponse, so FastAPI generates a 200 with an
    # empty schema — `agentcash check` reports `"outputSchema": {}` and the
    # operation earns SCHEMA_OUTPUT_MISSING. An agent deciding whether to spend
    # $0.01 cannot see what it gets back, which is the whole question.
    if not output_example:
        return
    ok = responses.setdefault("200", {"description": "Successful response"})
    schema = ((ok.get("content") or {}).get("application/json") or {}).get("schema") or {}
    # FastAPI emits `{"type": "object", "additionalProperties": true}` for a
    # handler with no response_model — truthy, and describes nothing. Only a
    # schema that names fields counts as already-documented.
    if schema.get("properties") or schema.get("$ref") or schema.get("items"):
        return
    ok["content"] = {
        "application/json": {
            "schema": _schema_from_example(output_example),
            "example": output_example,
        }
    }


def _has_param(parameters: list[dict[str, Any]], name: str) -> bool:
    return any(p.get("name") == name for p in parameters)


def _upsert_parameter(parameters: list[dict[str, Any]], param: dict[str, Any]) -> None:
    name = param.get("name")
    loc = param.get("in", "query")
    for idx, existing in enumerate(parameters):
        if existing.get("name") == name and existing.get("in", "query") == loc:
            parameters[idx] = dict(param)
            return
    parameters.append(dict(param))


def _merge_query_params(
    operation: dict[str, Any], *params: dict[str, Any]
) -> None:
    parameters = operation.setdefault("parameters", [])
    for param in params:
        _upsert_parameter(parameters, param)


_ADDRESS_QUERY_PARAM = {
    "name": "address",
    "in": "query",
    "required": True,
    "description": "Street address in the target city (1-120 characters).",
    "schema": {"type": "string", "minLength": 1, "maxLength": 120},
}

_AGENT_QUERY_PARAMS = (
    {
        "name": "city_code",
        "in": "query",
        "required": True,
        "description": "City code from GET /us/cities (e.g. mn, sea, nyc).",
        "schema": {"type": "string", "minLength": 1, "maxLength": 16},
    },
    {
        "name": "address",
        "in": "query",
        "required": True,
        "description": "Street address in that city (1-120 characters).",
        "schema": {"type": "string", "minLength": 1, "maxLength": 120},
    },
)

_TX_DECISION_QUERY_PARAMS = (
    {
        "name": "gas",
        "in": "query",
        "required": False,
        "description": "Gas preset eth|usdc|erc20|x402 or integer gas units.",
        "schema": {"type": "string"},
    },
    {
        "name": "urgency",
        "in": "query",
        "required": False,
        "description": "How soon the transaction must land: now, soon, or flexible.",
        "schema": {"type": "string", "enum": ["now", "soon", "flexible"]},
    },
)

_FINALITY_TX_PARAM = {
    "name": "tx",
    "in": "query",
    "required": True,
    "description": "Base mainnet transaction hash (0x + 64 hex).",
    "schema": {"type": "string", "pattern": "^0x[0-9a-fA-F]{64}$"},
}


def _apply_paid_input_schema(
    path: str, method: str, operation: dict[str, Any]
) -> None:
    """Declare business query/body inputs so indexers can construct calls."""
    if path in ("/mn/property-check",) or (
        path.startswith("/us/") and path.endswith("/property-check")
    ):
        if method == "get":
            _merge_query_params(operation, _ADDRESS_QUERY_PARAM)
        return
    if path == "/agent/property-due-diligence" and method == "get":
        _merge_query_params(operation, *_AGENT_QUERY_PARAMS)
        return
    if path == "/base/tx-decision" and method == "get":
        _merge_query_params(operation, *_TX_DECISION_QUERY_PARAMS)
        return
    if path == "/base/finality-check" and method == "get":
        _merge_query_params(operation, _FINALITY_TX_PARAM)
        return
    if path == "/tasks/us-rental-diligence" and method == "post":
        from app.diligence_pack import DISCOVERY_INPUT_EXAMPLE, DISCOVERY_INPUT_SCHEMA

        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": DISCOVERY_INPUT_SCHEMA,
                    "example": DISCOVERY_INPUT_EXAMPLE,
                }
            },
        }
        return
    if path == "/x402/policy-check" and method == "post":
        from app.policy_check import DISCOVERY_INPUT_EXAMPLE, DISCOVERY_INPUT_SCHEMA

        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": DISCOVERY_INPUT_SCHEMA,
                    "example": DISCOVERY_INPUT_EXAMPLE,
                }
            },
        }


def _city_operation_labels(city_code: str) -> tuple[str, str]:
    from app.city_compliance import registry as city_registry

    spec = city_registry.get_city(city_code).SPEC
    summary = spec.service_name
    description = spec.description or summary
    return summary, description


def tighten(schema: dict[str, Any]) -> dict[str, Any]:
    """Turn FastAPI's generated schema into the public discovery document."""
    priced = paid_paths()
    examples = output_examples()
    kept: dict[str, Any] = {}

    for path, operations in schema.get("paths", {}).items():
        amount = priced.get(path)
        if amount is None and path not in PUBLIC_FREE_PATHS:
            continue

        for method, operation in operations.items():
            if not isinstance(operation, dict):
                continue
            if amount is None:
                # Explicitly public, rather than merely undeclared.
                operation["security"] = []
            else:
                _declare_paid(operation, amount, examples.get(path))
                _apply_paid_input_schema(path, method, operation)
                if path == "/mn/property-check":
                    summary, description = _city_operation_labels("mn")
                    operation["summary"] = summary
                    operation["description"] = description
        kept[path] = operations

    # A concrete purchase URL the templated route cannot express. Re-point the
    # template at the pinned product and drop the now-satisfied path param.
    template = "/swarm/products/{product_id}/purchase"
    for path, amount in priced.items():
        if path in kept or not path.endswith("/purchase"):
            continue
        operations = schema.get("paths", {}).get(template)
        if not operations:
            continue
        concrete: dict[str, Any] = {}
        for method, operation in operations.items():
            if method != "get" or not isinstance(operation, dict):
                continue
            resolved = dict(operation)
            resolved["parameters"] = [
                p for p in resolved.get("parameters", [])
                if p.get("name") != "product_id"
            ]
            _declare_paid(resolved, amount, examples.get(path))
            _apply_paid_input_schema(path, method, resolved)
            concrete[method] = resolved
        if concrete:
            kept[path] = concrete

    # US city network: FastAPI only emits `/us/{city_code}/property-check`, but
    # agent_surface / paid_paths list concrete codes (`/us/sea/property-check`).
    # x402scan rejects registration when the exact resource path is missing from
    # openapi.json ("endpoint is not listed in the origin's openapi.json").
    city_template = "/us/{city_code}/property-check"
    city_ops = schema.get("paths", {}).get(city_template)
    if city_ops:
        for path, amount in priced.items():
            if path in kept:
                continue
            if not path.startswith("/us/") or not path.endswith("/property-check"):
                continue
            if "/sample" in path:
                continue
            concrete_city: dict[str, Any] = {}
            city_code = path.split("/")[2]
            for method, operation in city_ops.items():
                if method != "get" or not isinstance(operation, dict):
                    continue
                resolved = dict(operation)
                # Path param is baked into the concrete URL.
                resolved["parameters"] = [
                    p
                    for p in resolved.get("parameters", [])
                    if p.get("name") != "city_code"
                ]
                resolved["operationId"] = f"us_{city_code}_property_check_get"
                summary, description = _city_operation_labels(city_code)
                resolved["summary"] = summary
                resolved["description"] = description
                _declare_paid(resolved, amount, examples.get(path))
                _apply_paid_input_schema(path, method, resolved)
                concrete_city[method] = resolved
            if concrete_city:
                kept[path] = concrete_city

    schema["paths"] = kept
    components = schema.setdefault("components", {})
    components["securitySchemes"] = {"x402": X402_SECURITY_SCHEME}
    schema["info"]["x-guidance"] = GUIDANCE
    # x402scan verifies origin ownership from info.contact.email and shows it to
    # buyers as the way to reach the operator about an outage or a price change.
    # A URL alone does not satisfy that check. Operator-approved 2026-08-02.
    schema["info"]["contact"] = {
        "email": settings.contact_email,
        "url": "https://github.com/kwizzlesurp10-ctrl/x402-mcp/issues",
    }
    schema["servers"] = [{"url": settings.public_base_url.rstrip("/")}]

    # x402scan's preferred home for ownership proofs, ahead of the well-known
    # fan-out. Only present once the operator has actually signed one.
    proofs = agent_surface.ownership_proofs()
    if proofs:
        schema["x-discovery"] = {"ownershipProofs": proofs}
    return schema
