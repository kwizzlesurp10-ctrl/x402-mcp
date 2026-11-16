"""A2A JSON-RPC endpoint (message/send, tasks/get, tasks/cancel) with x402-a2a payments."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

from starlette.datastructures import Headers

from app.agent_surface import A2A_X402_EXTENSION_URI, A2A_X402_EXTENSION_URIS
from app.config import settings
from app import a2a_fulfillment_lock, a2a_task_store, demand, x402_latency

log = logging.getLogger("x402")

# x402-a2a metadata keys (standalone flow).
META_STATUS = "x402.payment.status"
META_REQUIRED = "x402.payment.required"
META_PAYLOAD = "x402.payment.payload"
META_RECEIPTS = "x402.payment.receipts"
META_ERROR = "x402.payment.error"
# Proves ownership for tasks/get, tasks/cancel, and paid message/send continuations.
META_TASK_CAPABILITY = "x402.task.capability"

JSONRPC_TASK_NOT_FOUND = -32001
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_FORBIDDEN = -32003
JSONRPC_INTERNAL_ERROR = -32603

# In-process cache when using Redis-backed persistence, or sole store when Redis off.
_TASKS_MEM: dict[str, dict[str, Any]] = {}

# Never echoed in JSON-RPC; use _client_task_view.
_INTERNAL_TASK_KEYS = frozenset(
    {
        "binding",
        "payment_required_header",
        "input",
        "product_id",
        "capability_token",
        "capability_digest",
        "client_id",
        "created_at_monotonic",
        "fulfillment_status",  # reconciliation hint; internal
        "fulfillment_done",
        a2a_task_store.TASK_REV_KEY,
    }
)

# Cheap abuse bound: new paid-task creations per client IP / minute.
_A2A_CREATE_WINDOW_S = 60.0
_A2A_CREATE_LIMIT = 30
_creation_buckets: dict[str, deque[float]] = defaultdict(deque)


def clear_task_store() -> None:
    """Test hook: drop in-memory A2A tasks."""
    _TASKS_MEM.clear()
    _creation_buckets.clear()
    a2a_task_store.clear_for_test()
    a2a_fulfillment_lock.clear_for_test()
    try:
        from app import x402_services
        from app.a2a_discovery import clear_discovery_cache_for_test
        from app import x402_latency

        x402_services.clear_resource_servers_for_test()
        clear_discovery_cache_for_test()
        x402_latency.clear_for_test()
    except Exception:  # noqa: BLE001
        pass


def _header(headers: Mapping[str, str] | Headers | None, name: str) -> str | None:
    if headers is None:
        return None
    raw = headers.get(name)
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _client_host_from_scope(request_scope: Mapping[str, Any] | None) -> str | None:
    if not request_scope:
        return None
    client = request_scope.get("client")
    if isinstance(client, (list, tuple)) and len(client) >= 1:
        host = client[0]
        return str(host) if host else None
    return None


def _creator_client_id(headers: Mapping[str, str] | Headers | None) -> str | None:
    return _header(headers, "x-a2a-client-id") or _header(headers, "a2a-client-id")


def _capability_from_task_ops(
    headers: Mapping[str, str] | Headers | None, params: dict[str, Any]
) -> str | None:
    cap = _header(headers, "x-a2a-task-capability") or _header(headers, "a2a-task-capability")
    if cap:
        return cap
    raw = params.get("capabilityToken")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _client_id_from_task_ops(
    headers: Mapping[str, str] | Headers | None, params: dict[str, Any]
) -> str | None:
    cid = _header(headers, "x-a2a-client-id") or _header(headers, "a2a-client-id")
    if cid:
        return cid
    raw = params.get("clientId")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _rate_limit_client_ip(
    headers: Mapping[str, str] | Headers | None,
    *,
    request_scope: Mapping[str, Any] | None = None,
) -> str:
    """Effective client IP for A2A creation rate limiting.

    ``CF-Connecting-IP``, ``X-Real-IP``, and ``X-Forwarded-For`` are all
    spoofable by a direct HTTP client. They are honored only when the TCP peer
    is a configured reverse proxy (``scope['x402.peer_trusted']``). Otherwise we
    use the socket client host from ASGI scope.
    """
    if headers is None:
        return "unknown"
    trusted = bool(request_scope and request_scope.get("x402.peer_trusted"))
    if trusted:
        for name in ("cf-connecting-ip", "x-real-ip"):
            raw = _header(headers, name)
            if raw:
                return raw.split(",")[0].strip() or "unknown"
        raw = _header(headers, "x-forwarded-for")
        if raw:
            return raw.split(",")[0].strip() or "unknown"
    direct = _client_host_from_scope(request_scope)
    return direct or "unknown"


def _check_a2a_creation_rate(
    headers: Mapping[str, str] | Headers | None,
    *,
    request_scope: Mapping[str, Any] | None = None,
) -> str | None:
    """Return error detail if over limit."""
    ip = _rate_limit_client_ip(headers, request_scope=request_scope)
    now = time.monotonic()
    q = _creation_buckets[ip]
    cutoff = now - _A2A_CREATE_WINDOW_S
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= _A2A_CREATE_LIMIT:
        return "a2a task creation rate limited"
    q.append(now)
    return None


def _capability_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _persist_task(task_id: str, record: dict[str, Any]) -> bool:
    rev_key = a2a_task_store.TASK_REV_KEY
    if a2a_task_store.durable_enabled():
        cur = a2a_task_store.get_task(task_id)
        if isinstance(cur, dict):
            cr = cur.get(rev_key)
            if isinstance(cr, int):
                record[rev_key] = cr
            else:
                # Legacy Redis payload without revision: treat as generation 0 for CAS.
                record[rev_key] = 0
    if not a2a_task_store.put_task(task_id, record):
        return False
    _TASKS_MEM[task_id] = record
    return True


def _persist_task_fail_response(
    req_id: Any, task_id: str, record: dict[str, Any]
) -> dict[str, Any] | None:
    """Return JSON-RPC error if durable persistence failed; else None."""
    if _persist_task(task_id, record):
        return None
    return _jsonrpc_error(
        req_id,
        JSONRPC_INTERNAL_ERROR,
        "task persistence unavailable",
        {"taskId": task_id},
    )


def _get_task_record(task_id: str) -> dict[str, Any] | None:
    mem = _TASKS_MEM.get(task_id)
    if a2a_task_store.durable_enabled():
        got = a2a_task_store.get_task(task_id)
        if got is None:
            if task_id in _TASKS_MEM:
                del _TASKS_MEM[task_id]
            return None
        _hydrate_task_record(task_id, got)
        if mem:
            bind = mem.get("binding")
            if bind is not None and got.get("binding") is None:
                got["binding"] = bind
            tok = mem.get("capability_token")
            if isinstance(tok, str) and tok and not got.get("capability_token"):
                got["capability_token"] = tok
        _TASKS_MEM[task_id] = got
        return got
    if mem is not None:
        return mem
    got = a2a_task_store.get_task(task_id)
    if got is None:
        return None
    _hydrate_task_record(task_id, got)
    _TASKS_MEM[task_id] = got
    return got


def _hydrate_task_record(task_id: str, record: dict[str, Any]) -> None:
    """Attach SkillBinding from skillId; mark failed if unknown."""
    if record.get("binding") is not None:
        return
    skill_id = record.get("skillId")
    if not isinstance(skill_id, str) or not skill_id:
        record["binding"] = None
        return
    bindings = _skill_bindings()
    binding = bindings.get(skill_id)
    if binding is None:
        msg = _agent_message(
            f"Task {task_id} cannot resume: skill {skill_id!r} is no longer available.",
            {},
        )
        record["status"] = {"state": "failed", "message": msg}
        record["binding"] = None
        return
    record["binding"] = binding


def _register_task(
    task_id: str, record: dict[str, Any], *, client_id: str | None
) -> bool:
    record["capability_token"] = secrets.token_urlsafe(32)
    record["capability_digest"] = _capability_digest(record["capability_token"])
    record["client_id"] = client_id
    record["created_at_monotonic"] = time.monotonic()
    record["fulfillment_done"] = False
    return _persist_task(task_id, record)


def _client_task_view(record: dict[str, Any]) -> dict[str, Any]:
    pub = {k: v for k, v in record.items() if k not in _INTERNAL_TASK_KEYS}
    tok = record.get("capability_token")
    if isinstance(tok, str) and tok:
        pub["capabilityToken"] = tok
    return pub


def _authorize_task_access(
    stored: dict[str, Any],
    *,
    capability: str | None,
    client_id: str | None,
) -> str | None:
    """Return an error detail if forbidden."""
    if not capability:
        return "missing task capability"
    want = stored.get("capability_digest")
    if isinstance(want, str) and len(want) == 64:
        got = _capability_digest(capability)
        if not secrets.compare_digest(want, got):
            return "invalid task capability"
    else:
        token = stored.get("capability_token")
        if not isinstance(token, str) or not token:
            return "task record missing capability"
        if not secrets.compare_digest(token, capability):
            return "invalid task capability"
    bound = stored.get("client_id")
    if isinstance(bound, str) and bound:
        if not client_id or not secrets.compare_digest(bound, client_id):
            return "client id does not match task binding"
    return None


@dataclass(frozen=True)
class SkillBinding:
    skill_id: str
    product_id: str
    price_usdc: str | None  # None => free
    build_payment_header: Callable[[], str] | None
    verify_and_settle: Callable[[str, str], Awaitable[dict[str, Any]]] | None
    validate_input: Callable[[dict[str, Any]], str | None]
    execute: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    record_revenue: Callable[[dict[str, Any], dict[str, Any]], None] | None = None
    payment_text: str = "Payment is required to run this skill."
    verify_payment: Callable[[str, str], Awaitable[dict[str, Any]]] | None = None
    settle_payment: Callable[[str, str], Awaitable[dict[str, Any]]] | None = None
    settle_after_fulfillment: bool = False


def _payment_required_body(header: str) -> dict[str, Any]:
    from x402.http import decode_payment_required_header

    pr = decode_payment_required_header(header)
    return pr.model_dump(by_alias=True, exclude_none=True)


def _encode_payload_as_signature(payload: Any) -> str:
    from x402.http import encode_payment_signature_header
    from x402.schemas import PaymentPayload

    if isinstance(payload, PaymentPayload):
        model = payload
    else:
        model = PaymentPayload.model_validate(payload)
    return encode_payment_signature_header(model)


def _settlement_receipt(settlement: dict[str, Any] | None, *, network: str) -> dict[str, Any]:
    settlement = settlement or {}
    tx = settlement.get("transaction") or settlement.get("txHash") or ""
    success = bool(settlement.get("success"))
    out: dict[str, Any] = {
        "success": success,
        "network": network,
        "transaction": str(tx) if tx else "",
    }
    if settlement.get("payer"):
        out["payer"] = str(settlement["payer"])
    if not success:
        out["errorReason"] = (
            settlement.get("errorReason")
            or settlement.get("error")
            or "settlement_failed"
        )
    return out


def _settlement_dict_from_receipts(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconstruct facilitator settlement fields from A2A receipt strip."""
    for r in reversed(receipts):
        if not r.get("success"):
            continue
        tx = r.get("transaction") or r.get("txHash")
        if not tx:
            continue
        return {
            "success": True,
            "transaction": str(tx),
            "txHash": str(tx),
            "payer": r.get("payer"),
        }
    return {}


def _task_dict(
    *,
    task_id: str,
    state: str,
    message: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    context_id: str | None = None,
) -> dict[str, Any]:
    status: dict[str, Any] = {"state": state}
    if message is not None:
        status["message"] = message
    out: dict[str, Any] = {
        "kind": "task",
        "id": task_id,
        "status": status,
    }
    if context_id:
        out["contextId"] = context_id
    if artifacts:
        out["artifacts"] = artifacts
    return out


def _agent_message(
    text: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "kind": "message",
        "role": "agent",
        "parts": [{"kind": "text", "text": text}],
        "metadata": metadata,
    }


def _artifact_from_result(result: dict[str, Any], name: str = "result.json") -> dict[str, Any]:
    return {
        "artifactId": uuid.uuid4().hex,
        "name": name,
        "parts": [{"kind": "data", "data": result}],
    }


def _skill_bindings() -> dict[str, SkillBinding]:
    from app import diligence_pack, policy_check, property_due_diligence_agent as pdd_agent, tx_decision
    from app.city_compliance import publish, registry

    bindings: dict[str, SkillBinding] = {}

    async def _tx_execute(inp: dict[str, Any]) -> dict[str, Any]:
        gas_raw = str(inp.get("gas") or "usdc")
        urgency = str(inp.get("urgency") or "flexible").strip().lower()
        gas_units = tx_decision.GAS_PRESETS.get(gas_raw.strip().lower())
        if gas_units is None:
            gas_units = int(gas_raw)
        return await tx_decision.advise(gas_units, urgency)

    def _tx_validate(inp: dict[str, Any]) -> str | None:
        urgency = str(inp.get("urgency") or "flexible").strip().lower()
        if urgency not in tx_decision.URGENCIES:
            return f"urgency must be one of {tx_decision.URGENCIES}"
        gas_raw = str(inp.get("gas") or "usdc").strip().lower()
        if gas_raw in tx_decision.GAS_PRESETS:
            return None
        try:
            gas_units = int(inp.get("gas") or gas_raw)
        except (TypeError, ValueError):
            return "gas must be eth|usdc|erc20|x402 or an integer in [21000, 30000000]"
        if not 21_000 <= gas_units <= 30_000_000:
            return "gas must be eth|usdc|erc20|x402 or an integer in [21000, 30000000]"
        return None

    bindings["base-tx-decision"] = SkillBinding(
        skill_id="base-tx-decision",
        product_id="base-tx-decision",
        price_usdc=settings.tx_decision_price,
        build_payment_header=tx_decision.build_payment_required_header,
        verify_and_settle=tx_decision.verify_and_settle,
        validate_input=_tx_validate,
        execute=_tx_execute,
        record_revenue=lambda st, _r: _record_product_revenue(
            "base-tx-decision", settings.tx_decision_price, st
        ),
        payment_text="Payment is required for Base transaction decision intelligence.",
    )

    if settings.x402_pay_to_address:
        from app import finality_check

        async def _fin_execute(inp: dict[str, Any]) -> dict[str, Any]:
            return await finality_check.check_finality(str(inp.get("tx") or ""))

        def _fin_validate(inp: dict[str, Any]) -> str | None:
            tx = str(inp.get("tx") or "").strip()
            if not tx.startswith("0x") or len(tx) != 66:
                return "tx must be a 0x-prefixed 32-byte transaction hash"
            return None

        bindings["base-finality-check"] = SkillBinding(
            skill_id="base-finality-check",
            product_id="base-finality-check",
            price_usdc=settings.finality_check_price,
            build_payment_header=finality_check.build_payment_required_header,
            verify_and_settle=finality_check.verify_and_settle,
            validate_input=_fin_validate,
            execute=_fin_execute,
            record_revenue=lambda st, _r: _record_product_revenue(
                "base-finality-check", settings.finality_check_price, st
            ),
            payment_text="Payment is required for Base transaction finality classification.",
        )

    async def _catalog_execute(_inp: dict[str, Any]) -> dict[str, Any]:
        return {
            "network": "us-city-open-data-compliance",
            "cities": registry.list_cities(),
            "catalog_url": f"{settings.public_base_url.rstrip('/')}/us/cities",
        }

    bindings["us-cities-catalog"] = SkillBinding(
        skill_id="us-cities-catalog",
        product_id="us-cities-catalog",
        price_usdc=None,
        build_payment_header=None,
        verify_and_settle=None,
        validate_input=lambda _inp: None,
        execute=_catalog_execute,
    )

    async def _diligence_execute(inp: dict[str, Any]) -> dict[str, Any]:
        body = diligence_pack.DiligencePackRequest.model_validate(inp)
        return await diligence_pack.build_pack(body, payment_settled=True)

    def _diligence_validate(inp: dict[str, Any]) -> str | None:
        try:
            diligence_pack.DiligencePackRequest.model_validate(inp)
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        return None

    bindings["us-rental-diligence-pack"] = SkillBinding(
        skill_id="us-rental-diligence-pack",
        product_id=diligence_pack.PRODUCT_ID,
        price_usdc=diligence_pack.price_string(),
        build_payment_header=diligence_pack.build_payment_required_header,
        verify_and_settle=diligence_pack.verify_and_settle,
        validate_input=_diligence_validate,
        execute=_diligence_execute,
        record_revenue=lambda st, _r: _record_product_revenue(
            diligence_pack.PRODUCT_ID, diligence_pack.price_string(), st
        ),
        payment_text="Payment is required for the US multi-city rental diligence pack.",
    )

    if settings.policy_check_enabled and settings.x402_pay_to_address:

        async def _policy_check_execute(inp: dict[str, Any]) -> dict[str, Any]:
            body = policy_check.PolicyCheckBody.model_validate(
                {
                    "payment_required_header": inp.get("payment_required_header"),
                    "policy": inp.get("policy") or {},
                    "request_digest": inp.get("request_digest"),
                    "idempotency_key": inp.get("idempotency_key"),
                }
            )
            settlement = inp.get("_a2a_settlement") or {}
            if not isinstance(settlement, dict):
                settlement = {}
            return policy_check.build_paid_analysis_dict(body, settlement=settlement)

        def _policy_check_validate(inp: dict[str, Any]) -> str | None:
            try:
                policy_check.PolicyCheckBody.model_validate(
                    {
                        "payment_required_header": inp.get("payment_required_header"),
                        "policy": inp.get("policy") or {},
                        "request_digest": inp.get("request_digest"),
                        "idempotency_key": inp.get("idempotency_key"),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                return str(exc)
            return None

        bindings["buyer-payment-policy-check"] = SkillBinding(
            skill_id="buyer-payment-policy-check",
            product_id=policy_check.PRODUCT_ID,
            price_usdc=policy_check.price_string(),
            build_payment_header=policy_check.build_payment_required_header,
            verify_and_settle=policy_check.verify_and_settle,
            validate_input=_policy_check_validate,
            execute=_policy_check_execute,
            record_revenue=lambda st, _r: _record_product_revenue(
                policy_check.PRODUCT_ID, policy_check.price_string(), st
            ),
            payment_text="Payment is required for offline buyer payment-policy consistency analysis.",
        )

    async def _pdd_execute(inp: dict[str, Any]) -> dict[str, Any]:
        return await pdd_agent.run_check(
            city_code=str(inp.get("city_code") or ""),
            address=str(inp.get("address") or ""),
        )

    def _pdd_validate(inp: dict[str, Any]) -> str | None:
        code = str(inp.get("city_code") or "").strip().lower()
        addr = str(inp.get("address") or "").strip()
        if code not in registry.CITIES:
            return f"city_code must be one of {sorted(registry.CITIES)}"
        if not addr or len(addr) > 120:
            return "address must be 1-120 chars"
        return None

    bindings["property-due-diligence-agent"] = SkillBinding(
        skill_id="property-due-diligence-agent",
        product_id=pdd_agent.PRODUCT_ID,
        price_usdc=pdd_agent.PRICE,
        build_payment_header=pdd_agent.build_payment_required_header,
        verify_and_settle=pdd_agent.verify_and_settle,
        verify_payment=pdd_agent.verify_payment,
        settle_payment=pdd_agent.settle_payment,
        settle_after_fulfillment=True,
        validate_input=_pdd_validate,
        execute=_pdd_execute,
        record_revenue=lambda st, _r: _record_product_revenue(
            pdd_agent.PRODUCT_ID, pdd_agent.PRICE, st
        ),
        payment_text="Payment is required for the property due diligence agent.",
    )

    for entry in registry.list_cities():
        code = entry["code"]
        skill_id = f"property-check-{code}"

        async def _city_execute(
            inp: dict[str, Any], *, city_code: str = code
        ) -> dict[str, Any]:
            mod = registry.get_city(city_code)
            spec = mod.SPEC
            addr = str(inp.get("address") or "")
            raw = await mod.check_property(addr)
            if not isinstance(raw, dict):
                raw = {"result": raw}
            out = publish.prepare_city_report(raw, spec=spec, address_fallback=addr)
            out["payment_settled"] = True
            return out

        def _city_validate(inp: dict[str, Any]) -> str | None:
            addr = str(inp.get("address") or "").strip()
            if not addr or len(addr) > 120:
                return "address must be 1-120 chars"
            return None

        from app.city_compliance import gate as city_gate, publish

        mod = registry.get_city(code)
        spec = mod.SPEC
        input_example = {"address": spec.sample_address}
        output_example = publish.discovery_output_example(mod)
        pid = city_gate.product_id(spec)

        bindings[skill_id] = SkillBinding(
            skill_id=skill_id,
            product_id=pid,
            price_usdc=entry["price"],
            # Bind the loop's spec/examples as default args: a plain lambda would
            # late-bind them, so every city skill would serve the LAST city's
            # challenge (all 17 pointed at San Diego).
            build_payment_header=lambda _spec=spec, _inp=input_example, _out=output_example: (
                city_gate.build_payment_required_header(
                    _spec,
                    input_example=_inp,
                    output_example=_out,
                )
            ),
            verify_and_settle=city_gate.verify_and_settle,
            verify_payment=city_gate.verify_payment,
            settle_payment=city_gate.settle_payment,
            settle_after_fulfillment=True,
            validate_input=_city_validate,
            execute=_city_execute,
            record_revenue=lambda st, _r, p=pid, pr=entry["price"]: _record_product_revenue(
                p, pr, st
            ),
            payment_text=f"Payment is required for {entry['name']} property compliance check.",
        )

    return bindings


def _record_product_revenue(
    product_id: str,
    price: str,
    settlement: dict[str, Any],
) -> None:
    try:
        from app.swarm import ledger_writer
        from app.swarm.publisher import parse_price_usdc

        tx = settlement.get("transaction") or settlement.get("txHash")
        ledger_writer.record_revenue(
            agent_id=product_id,
            amount_usdc=parse_price_usdc(price),
            network=settings.x402_default_network,
            product_id=product_id,
            tx=str(tx) if tx else None,
            payer=settlement.get("payer"),
        )
    except Exception:  # noqa: BLE001
        log.warning("a2a revenue ledger write failed product=%s", product_id, exc_info=True)


# The agent card advertises the generic ``us-city-property-check`` skill
# (input: city_code + address). Route it to the per-city binding so agents
# that discover the network skill (e.g. "Minneapolis, city_code=mn") can buy
# it over A2A instead of getting "unknown skillId".
CITY_NETWORK_SKILL_ID = "us-city-property-check"


def _resolve_city_network_alias(
    skill_id: str,
    skill_input: dict[str, Any],
    bindings: dict[str, SkillBinding],
) -> tuple[str, dict[str, Any], str | None]:
    if skill_id != CITY_NETWORK_SKILL_ID:
        return skill_id, skill_input, None
    code = str(skill_input.get("city_code") or "").strip().lower()
    target = f"property-check-{code}" if code else ""
    if not code or target not in bindings:
        codes = sorted(
            k.removeprefix("property-check-") for k in bindings if k.startswith("property-check-")
        )
        return skill_id, skill_input, f"city_code must be one of {codes}"
    rest = {k: v for k, v in skill_input.items() if k != "city_code"}
    return target, rest, None


def _resolve_skill_id(message: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    meta = message.get("metadata") or {}
    skill_id = meta.get("skillId") or meta.get("skill_id")
    inp = meta.get("input")
    if isinstance(inp, dict):
        skill_input = dict(inp)
    else:
        skill_input = {}

    for part in message.get("parts") or []:
        if part.get("kind") != "data":
            continue
        data = part.get("data")
        if not isinstance(data, dict):
            continue
        skill_id = skill_id or data.get("skillId") or data.get("skill_id")
        nested = data.get("input")
        if isinstance(nested, dict):
            skill_input = {**skill_input, **nested}
        else:
            skill_input = {**skill_input, **data}
        break

    for part in message.get("parts") or []:
        if part.get("kind") != "text":
            continue
        text = (part.get("text") or "").strip()
        if not text.startswith("{"):
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            skill_id = skill_id or parsed.get("skillId") or parsed.get("skill_id")
            nested = parsed.get("input")
            if isinstance(nested, dict):
                skill_input = {**skill_input, **nested}
            else:
                skill_input = {**skill_input, **parsed}
        break

    return skill_id, skill_input


def _jsonrpc_error(req_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _jsonrpc_result(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _normalize_method(method: str) -> str | None:
    m = (method or "").strip()
    aliases = {
        "SendMessage": "message/send",
        "message/send": "message/send",
        "GetTask": "tasks/get",
        "tasks/get": "tasks/get",
        "CancelTask": "tasks/cancel",
        "tasks/cancel": "tasks/cancel",
    }
    return aliases.get(m)


async def handle_jsonrpc(
    body: dict[str, Any],
    *,
    user_agent: str | None = None,
    headers: Mapping[str, str] | Headers | None = None,
    request_scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch one JSON-RPC 2.0 request for POST /a2a."""
    req_id = body.get("id")
    method = _normalize_method(str(body.get("method") or ""))
    if not method:
        return _jsonrpc_error(req_id, JSONRPC_METHOD_NOT_FOUND, "method not found")

    params = body.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, "params must be an object")

    if method == "message/send":
        creator = _creator_client_id(headers)
        return await _message_send(
            req_id,
            params,
            user_agent=user_agent,
            creator_client_id=creator,
            headers=headers,
            request_scope=request_scope,
        )
    if method == "tasks/get":
        return _tasks_get(req_id, params, headers=headers)
    if method == "tasks/cancel":
        return _tasks_cancel(req_id, params, headers=headers)
    return _jsonrpc_error(req_id, JSONRPC_METHOD_NOT_FOUND, "method not found")


async def _message_send(
    req_id: Any,
    params: dict[str, Any],
    *,
    user_agent: str | None,
    creator_client_id: str | None = None,
    headers: Mapping[str, str] | Headers | None = None,
    request_scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from app import demand

    message = params.get("message")
    if not isinstance(message, dict):
        return _jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, "message required")

    meta = message.get("metadata") or {}
    pay_status = meta.get(META_STATUS)
    task_id = message.get("taskId") or message.get("task_id")

    if pay_status == "payment-rejected":
        tid = task_id or uuid.uuid4().hex
        msg = _agent_message(
            "Payment requirements rejected by client.",
            {META_STATUS: "payment-rejected"},
        )
        task = _task_dict(task_id=tid, state="canceled", message=msg)
        rec = {**task}
        if not _register_task(tid, rec, client_id=creator_client_id):
            pe = _persist_task_fail_response(req_id, tid, rec)
            if pe is not None:
                return pe
        return _jsonrpc_result(req_id, _client_task_view(rec))

    payload_obj = meta.get(META_PAYLOAD)
    if pay_status == "payment-submitted" or payload_obj is not None:
        if not task_id:
            return _jsonrpc_error(
                req_id,
                JSONRPC_TASK_NOT_FOUND,
                "task not found",
                {"taskId": task_id},
            )
        stored0 = _get_task_record(task_id)
        if stored0 is None:
            return _jsonrpc_error(
                req_id,
                JSONRPC_TASK_NOT_FOUND,
                "task not found",
                {"taskId": task_id},
            )
        cap = meta.get(META_TASK_CAPABILITY) or meta.get("taskCapability")
        if isinstance(cap, str) and cap.strip():
            cap = cap.strip()
        else:
            cap = None
        reason = _authorize_task_access(
            stored0,
            capability=cap,
            client_id=creator_client_id,
        )
        if reason:
            return _jsonrpc_error(
                req_id,
                JSONRPC_FORBIDDEN,
                reason,
                {"taskId": task_id, "detail": reason},
            )
        return await _continue_paid_task(req_id, task_id, payload_obj, user_agent=user_agent)

    skill_id, skill_input = _resolve_skill_id(message)
    if not skill_id:
        return _jsonrpc_error(
            req_id,
            JSONRPC_INVALID_PARAMS,
            "skillId required in message metadata or data part",
        )

    bindings = _skill_bindings()
    skill_id, skill_input, alias_err = _resolve_city_network_alias(skill_id, skill_input, bindings)
    if alias_err:
        return _jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, alias_err)
    binding = bindings.get(skill_id)
    if binding is None:
        return _jsonrpc_error(
            req_id,
            JSONRPC_INVALID_PARAMS,
            f"unknown skillId: {skill_id}",
        )

    err = binding.validate_input(skill_input)
    if err:
        tid = uuid.uuid4().hex
        msg = _agent_message(f"Invalid input: {err}", {})
        task = _task_dict(task_id=tid, state="failed", message=msg)
        return _jsonrpc_result(req_id, task)

    if binding.price_usdc is None:
        result = await binding.execute(skill_input)
        tid = uuid.uuid4().hex
        msg = _agent_message("Skill completed.", {})
        task = _task_dict(
            task_id=tid,
            state="completed",
            message=msg,
            artifacts=[_artifact_from_result(result)],
        )
        rec = {**task, "skillId": skill_id, "input": skill_input}
        if not _register_task(tid, rec, client_id=creator_client_id):
            pe = _persist_task_fail_response(req_id, tid, rec)
            if pe is not None:
                return pe
        return _jsonrpc_result(req_id, _client_task_view(rec))

    if not settings.x402_pay_to_address:
        return _jsonrpc_error(req_id, -32004, "seller not configured")

    rl = _check_a2a_creation_rate(headers, request_scope=request_scope)
    if rl:
        return _jsonrpc_error(req_id, JSONRPC_INVALID_PARAMS, rl)

    t_ch0 = time.perf_counter()
    try:
        assert binding.build_payment_header is not None
        header = binding.build_payment_header()
        required_body = _payment_required_body(header)
    except Exception:  # noqa: BLE001
        log.warning("a2a: cannot build payment challenge skill=%s", skill_id, exc_info=True)
        return _jsonrpc_error(req_id, -32004, "challenge unavailable")
    x402_latency.record_span("a2a", "challenge_build", t_ch0)

    tid = uuid.uuid4().hex
    hdrs = Headers({"user-agent": user_agent or ""})
    if not demand.is_self_traffic(hdrs):
        demand.record_challenge(binding.product_id, user_agent)

    pay_meta = {
        META_STATUS: "payment-required",
        META_REQUIRED: required_body,
    }
    msg = _agent_message(binding.payment_text, pay_meta)
    task = _task_dict(task_id=tid, state="input-required", message=msg)
    rec = {
        **task,
        "skillId": skill_id,
        "input": skill_input,
        "product_id": binding.product_id,
        "payment_required_header": header,
        "receipts": [],
        "binding": binding,
    }
    if not _register_task(tid, rec, client_id=creator_client_id):
        pe = _persist_task_fail_response(req_id, tid, rec)
        if pe is not None:
            return pe
    return _jsonrpc_result(req_id, _client_task_view(rec))


async def _continue_paid_task(
    req_id: Any,
    task_id: str,
    payload_obj: Any,
    *,
    user_agent: str | None,
) -> dict[str, Any]:
    stored = _get_task_record(task_id)
    if stored is None:
        return _jsonrpc_error(
            req_id,
            JSONRPC_TASK_NOT_FOUND,
            "task not found",
            {"taskId": task_id},
        )
    binding = stored.get("binding")
    header = stored.get("payment_required_header")
    network = settings.x402_default_network

    state = (stored.get("status") or {}).get("state")
    if state == "canceled":
        return _jsonrpc_error(
            req_id,
            JSONRPC_FORBIDDEN,
            "task canceled",
            {"taskId": task_id, "detail": "canceled"},
        )

    # Paid work already delivered — safe retries return the same view without re-execution.
    if state == "completed" and stored.get("fulfillment_done"):
        return _jsonrpc_result(req_id, _client_task_view(stored))

    # Idempotent retry: facilitator already returned tx in a prior attempt; do not re-verify.
    had_success_tx = False
    for r in list(stored.get("receipts") or []):
        if r.get("success") and (r.get("transaction") or r.get("txHash")):
            had_success_tx = True
            break
    if had_success_tx and not stored.get("fulfillment_done"):
        if binding is None or not hasattr(binding, "execute"):
            return _jsonrpc_result(req_id, _client_task_view(stored))
        receipts = list(stored.get("receipts") or [])
        skill_input = stored.get("input") or {}
        if stored.get("skillId") == "buyer-payment-policy-check":
            skill_input = dict(skill_input)
            skill_input["_a2a_settlement"] = _settlement_dict_from_receipts(receipts)
        if not a2a_fulfillment_lock.try_acquire(task_id):
            msg = _agent_message(
                "Fulfillment in progress on another worker; poll tasks/get.",
                {META_STATUS: "payment-completed", META_RECEIPTS: receipts},
            )
            task = _task_dict(task_id=task_id, state="working", message=msg)
            stored.update(task)
            if not _persist_task(task_id, stored):
                return _jsonrpc_error(
                    req_id,
                    JSONRPC_INTERNAL_ERROR,
                    "task persistence unavailable",
                    {"taskId": task_id},
                )
            return _jsonrpc_result(req_id, _client_task_view(stored))
        out2: dict[str, Any] | None = None
        try:
            te0 = time.perf_counter()
            deliverable = await binding.execute(skill_input)
            x402_latency.record_span("a2a", "fulfillment_execute_retry", te0)
            msg = _agent_message(
                "Payment completed. Skill result attached as artifact.",
                {META_STATUS: "payment-completed", META_RECEIPTS: receipts},
            )
            task = _task_dict(
                task_id=task_id,
                state="completed",
                message=msg,
                artifacts=[_artifact_from_result(deliverable)],
            )
            stored.update(task)
            stored["fulfillment_done"] = True
            if not _persist_task(task_id, stored):
                out2 = _jsonrpc_error(
                    req_id,
                    JSONRPC_INTERNAL_ERROR,
                    "task persistence unavailable",
                    {"taskId": task_id},
                )
            else:
                out2 = _jsonrpc_result(req_id, _client_task_view(stored))
        except Exception:  # noqa: BLE001
            log.warning("a2a skill execution retry failed", exc_info=True)
            msg = _agent_message(
                "Payment settled but skill execution failed.",
                {META_STATUS: "payment-completed", META_RECEIPTS: receipts},
            )
            task = _task_dict(task_id=task_id, state="failed", message=msg)
            stored.update(task)
            if not _persist_task(task_id, stored):
                out2 = _jsonrpc_error(
                    req_id,
                    JSONRPC_INTERNAL_ERROR,
                    "task persistence unavailable",
                    {"taskId": task_id},
                )
            else:
                out2 = _jsonrpc_result(req_id, _client_task_view(stored))
        finally:
            a2a_fulfillment_lock.release(task_id)
        assert out2 is not None
        return out2

    if not isinstance(header, str) or not header:
        msg = _agent_message("Task is missing payment challenge context.", {})
        task = _task_dict(task_id=task_id, state="failed", message=msg)
        stored.update(task)
        if not _persist_task(task_id, stored):
            return _jsonrpc_error(
                req_id,
                JSONRPC_INTERNAL_ERROR,
                "task persistence unavailable",
                {"taskId": task_id},
            )
        return _jsonrpc_result(req_id, _client_task_view(stored))

    if not isinstance(binding, SkillBinding):
        return _jsonrpc_result(req_id, _client_task_view(stored))

    try:
        signature = _encode_payload_as_signature(payload_obj)
    except Exception as exc:  # noqa: BLE001
        receipt = _settlement_receipt({"success": False, "errorReason": str(exc)}, network=network)
        receipts = list(stored.get("receipts") or []) + [receipt]
        msg = _agent_message(
            "Payment payload could not be parsed.",
            {
                META_STATUS: "payment-failed",
                META_ERROR: "INVALID_SIGNATURE",
                META_RECEIPTS: receipts,
            },
        )
        task = _task_dict(task_id=task_id, state="failed", message=msg)
        stored.update(task)
        stored["receipts"] = receipts
        if not _persist_task(task_id, stored):
            return _jsonrpc_error(
                req_id,
                JSONRPC_INTERNAL_ERROR,
                "task persistence unavailable",
                {"taskId": task_id},
            )
        return _jsonrpc_result(req_id, _client_task_view(stored))

    policy_pc_body: Any = None
    policy_pc_claim_key: str | None = None

    if stored.get("skillId") == "buyer-payment-policy-check":
        from app import policy_check as pc

        inp = stored.get("input") or {}
        try:
            body = pc.PolicyCheckBody.model_validate(
                {
                    "payment_required_header": inp.get("payment_required_header"),
                    "policy": inp.get("policy") or {},
                    "request_digest": inp.get("request_digest"),
                    "idempotency_key": inp.get("idempotency_key"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            msg = _agent_message(f"Invalid policy-check input: {exc}", {})
            task = _task_dict(task_id=task_id, state="failed", message=msg)
            stored.update(task)
            if not _persist_task(task_id, stored):
                return _jsonrpc_error(
                    req_id,
                    JSONRPC_INTERNAL_ERROR,
                    "task persistence unavailable",
                    {"taskId": task_id},
                )
            return _jsonrpc_result(req_id, _client_task_view(stored))

        ok_sem, sem_detail = pc.preflight_semantic_ok(body)
        if not ok_sem:
            msg = _agent_message(
                f"Inspected request not processable: {sem_detail}",
                {META_STATUS: "payment-failed", META_ERROR: "INSPECTED_INVALID"},
            )
            task = _task_dict(task_id=task_id, state="input-required", message=msg)
            stored.update(task)
            if not _persist_task(task_id, stored):
                return _jsonrpc_error(
                    req_id,
                    JSONRPC_INTERNAL_ERROR,
                    "task persistence unavailable",
                    {"taskId": task_id},
                )
            return _jsonrpc_result(req_id, _client_task_view(stored))

        verified = await pc.verify_payment_only(signature, header)
        if not verified.get("is_valid"):
            receipt = _settlement_receipt({"success": False}, network=network)
            receipt["errorReason"] = str(verified.get("invalid_reason") or "invalid_signature")
            receipts = list(stored.get("receipts") or []) + [receipt]
            required_body = _payment_required_body(header)
            msg = _agent_message(
                "Payment verification failed.",
                {
                    META_STATUS: "payment-failed",
                    META_ERROR: "INVALID_SIGNATURE",
                    META_REQUIRED: required_body,
                    META_RECEIPTS: receipts,
                },
            )
            task = _task_dict(task_id=task_id, state="input-required", message=msg)
            stored.update(task)
            stored["receipts"] = receipts
            if not _persist_task(task_id, stored):
                return _jsonrpc_error(
                    req_id,
                    JSONRPC_INTERNAL_ERROR,
                    "task persistence unavailable",
                    {"taskId": task_id},
                )
            return _jsonrpc_result(req_id, _client_task_view(stored))

        proof_fp, _ = pc.payment_proof_fingerprint(signature, header)
        payer_fp = pc.payer_fingerprint_from_decoded_proof(signature, header)
        if proof_fp is None or payer_fp is None:
            msg = _agent_message("Malformed payment proof.", {META_STATUS: "payment-failed"})
            task = _task_dict(task_id=task_id, state="failed", message=msg)
            stored.update(task)
            if not _persist_task(task_id, stored):
                return _jsonrpc_error(
                    req_id,
                    JSONRPC_INTERNAL_ERROR,
                    "task persistence unavailable",
                    {"taskId": task_id},
                )
            return _jsonrpc_result(req_id, _client_task_view(stored))

        input_digest = pc.analysis_input_digest(
            inspected_header_digest=pc.inspected_header_digest(body.payment_required_header),
            policy=body.policy,
            request_digest=body.request_digest,
        )
        claim_key = pc.policy_check_claim_key(body, payer_fp=payer_fp, proof_fp=proof_fp)
        policy_pc_body = body
        policy_pc_claim_key = claim_key

        claim_st, claim_rec = await pc.delivery_try_claim_or_hit_async(claim_key, input_digest)
        if claim_st == "redis_error":
            return _jsonrpc_error(
                req_id,
                JSONRPC_INTERNAL_ERROR,
                "delivery coordination unavailable",
                {"taskId": task_id},
            )
        if claim_st == "conflict":
            msg = _agent_message(
                "Idempotency conflict: same key with different analysis inputs.",
                {META_STATUS: "payment-failed", META_ERROR: "IDEMPOTENCY_CONFLICT"},
            )
            task = _task_dict(task_id=task_id, state="failed", message=msg)
            stored.update(task)
            if not _persist_task(task_id, stored):
                return _jsonrpc_error(
                    req_id,
                    JSONRPC_INTERNAL_ERROR,
                    "task persistence unavailable",
                    {"taskId": task_id},
                )
            return _jsonrpc_result(req_id, _client_task_view(stored))

        if claim_st == "final_hit" and isinstance(claim_rec, dict) and isinstance(claim_rec.get("body"), dict):
            msg = _agent_message(
                "Payment completed. Skill result attached as artifact.",
                {META_STATUS: "payment-completed"},
            )
            task = _task_dict(
                task_id=task_id,
                state="completed",
                message=msg,
                artifacts=[_artifact_from_result(claim_rec["body"])],
            )
            stored.update(task)
            stored["fulfillment_done"] = True
            if not _persist_task(task_id, stored):
                return _jsonrpc_error(
                    req_id,
                    JSONRPC_INTERNAL_ERROR,
                    "task persistence unavailable",
                    {"taskId": task_id},
                )
            return _jsonrpc_result(req_id, _client_task_view(stored))

        if claim_st == "claimed_busy":
            waited = await pc.delivery_wait_for_final_async(claim_key, input_digest)
            if isinstance(waited, dict):
                msg = _agent_message(
                    "Payment completed. Skill result attached as artifact.",
                    {META_STATUS: "payment-completed"},
                )
                task = _task_dict(
                    task_id=task_id,
                    state="completed",
                    message=msg,
                    artifacts=[_artifact_from_result(waited)],
                )
                stored.update(task)
                stored["fulfillment_done"] = True
                if not _persist_task(task_id, stored):
                    return _jsonrpc_error(
                        req_id,
                        JSONRPC_INTERNAL_ERROR,
                        "task persistence unavailable",
                        {"taskId": task_id},
                    )
                return _jsonrpc_result(req_id, _client_task_view(stored))
            return _jsonrpc_error(
                req_id,
                JSONRPC_INTERNAL_ERROR,
                "delivery in progress; retry shortly",
                {"taskId": task_id},
            )

        tv0 = time.perf_counter()
        result = await pc.verify_and_settle_after_claim(
            signature,
            header,
            claim_key=claim_key,
            input_digest=input_digest,
        )
    else:
        deferred_settle = (
            binding.settle_after_fulfillment
            and binding.verify_payment is not None
            and binding.settle_payment is not None
        )
        tv0 = time.perf_counter()
        if deferred_settle:
            assert binding.verify_payment is not None
            result = await binding.verify_payment(signature, header)
            result = {
                **result,
                "payment_settled": False,
                "settlement": None,
                "settlement_error": None,
            }
            stored["settle_after_fulfillment"] = True
        else:
            assert binding.verify_and_settle is not None
            result = await binding.verify_and_settle(signature, header)
    x402_latency.record_span("a2a", "verify_settle", tv0)
    settlement = result.get("settlement") or {}
    receipt = _settlement_receipt(settlement, network=network)
    if not result.get("is_valid"):
        receipt["success"] = False
        receipt["errorReason"] = result.get("invalid_reason") or "invalid_signature"
    elif stored.get("settle_after_fulfillment"):
        receipt["success"] = True
        receipt["deferredSettlement"] = True
    receipts = list(stored.get("receipts") or []) + [receipt]

    payment_ok = result.get("is_valid") and (
        result.get("payment_settled") or stored.get("settle_after_fulfillment")
    )
    if not payment_ok:
        if stored.get("skillId") == "buyer-payment-policy-check" and policy_pc_claim_key:
            from app import policy_check as pc

            pc.delivery_abort_claim_sync(policy_pc_claim_key)
        required_body = _payment_required_body(header)
        msg = _agent_message(
            "Payment verification or settlement failed.",
            {
                META_STATUS: "payment-failed",
                META_ERROR: "INVALID_SIGNATURE",
                META_REQUIRED: required_body,
                META_RECEIPTS: receipts,
            },
        )
        task = _task_dict(task_id=task_id, state="input-required", message=msg)
        stored.update(task)
        stored["receipts"] = receipts
        if not _persist_task(task_id, stored):
            return _jsonrpc_error(
                req_id,
                JSONRPC_INTERNAL_ERROR,
                "task persistence unavailable",
                {"taskId": task_id},
            )
        return _jsonrpc_result(req_id, _client_task_view(stored))

    if (
        stored.get("skillId") == "buyer-payment-policy-check"
        and policy_pc_body is not None
        and policy_pc_claim_key
    ):
        from app import policy_check as pc

        body_pc = policy_pc_body
        claim_key = policy_pc_claim_key
        input_digest_done = pc.analysis_input_digest(
            inspected_header_digest=pc.inspected_header_digest(body_pc.payment_required_header),
            policy=body_pc.policy,
            request_digest=body_pc.request_digest,
        )
        tx_present_pc = bool((settlement or {}).get("transaction") or (settlement or {}).get("txHash"))
        if result.get("payment_settled") and not tx_present_pc:
            pc.delivery_abort_claim_sync(claim_key)
            msg = _agent_message(
                "Settlement succeeded without an on-chain transaction id; manual reconciliation required.",
                {META_STATUS: "payment-completed", META_RECEIPTS: receipts},
            )
            task = _task_dict(task_id=task_id, state="input-required", message=msg)
            stored.update(task)
            stored["receipts"] = receipts
            if not _persist_task(task_id, stored):
                return _jsonrpc_error(
                    req_id,
                    JSONRPC_INTERNAL_ERROR,
                    "task persistence unavailable",
                    {"taskId": task_id},
                )
            return _jsonrpc_result(req_id, _client_task_view(stored))

        proof_fp_done, _ = pc.payment_proof_fingerprint(signature, header)
        if proof_fp_done is None:
            proof_fp_done = ""

        deliverable_pc = pc.build_paid_analysis_dict(body_pc, settlement=settlement)
        written_pc, _ = await pc.delivery_write_final_async(
            claim_key,
            input_digest=input_digest_done,
            body=deliverable_pc,
            payment_proof_fp=proof_fp_done,
        )
        if not written_pc:
            pc.delivery_abort_claim_sync(claim_key)
            return _jsonrpc_error(
                req_id,
                JSONRPC_INTERNAL_ERROR,
                "delivery persist failed after settlement",
                {"taskId": task_id},
            )

        if binding.record_revenue:
            binding.record_revenue(settlement, stored.get("input") or {})

        msg = _agent_message(
            "Payment completed. Skill result attached as artifact.",
            {
                META_STATUS: "payment-completed",
                META_RECEIPTS: receipts,
            },
        )
        task = _task_dict(
            task_id=task_id,
            state="completed",
            message=msg,
            artifacts=[_artifact_from_result(deliverable_pc)],
        )
        stored.update(task)
        stored["receipts"] = receipts
        stored["fulfillment_done"] = True
        if not _persist_task(task_id, stored):
            return _jsonrpc_error(
                req_id,
                JSONRPC_INTERNAL_ERROR,
                "task persistence unavailable",
                {"taskId": task_id},
            )
        return _jsonrpc_result(req_id, _client_task_view(stored))

    if binding.record_revenue and not stored.get("settle_after_fulfillment"):
        binding.record_revenue(settlement, stored.get("input") or {})

    skill_input = stored.get("input") or {}
    if stored.get("skillId") == "buyer-payment-policy-check":
        skill_input = dict(skill_input)
        skill_input["_a2a_settlement"] = settlement
    settled_ok = bool(result.get("payment_settled"))
    tx_present = bool((settlement or {}).get("transaction") or (settlement or {}).get("txHash"))
    if settled_ok and tx_present:
        stored["fulfillment_status"] = "fulfilled"
    elif settled_ok:
        stored["fulfillment_status"] = "settled_pending_tx"
    else:
        stored["fulfillment_status"] = "unknown_settlement"

    # Settlement accepted but tx missing — do not run expensive work (matches MCP ambiguity policy).
    if settled_ok and not tx_present:
        msg = _agent_message(
            "Settlement succeeded without an on-chain transaction id; manual reconciliation required.",
            {META_STATUS: "payment-completed", META_RECEIPTS: receipts},
        )
        task = _task_dict(task_id=task_id, state="input-required", message=msg)
        stored.update(task)
        stored["receipts"] = receipts
        if not _persist_task(task_id, stored):
            return _jsonrpc_error(
                req_id,
                JSONRPC_INTERNAL_ERROR,
                "task persistence unavailable",
                {"taskId": task_id},
            )
        return _jsonrpc_result(req_id, _client_task_view(stored))

    if stored.get("fulfillment_done"):
        return _jsonrpc_result(req_id, _client_task_view(stored))

    if not a2a_fulfillment_lock.try_acquire(task_id):
        msg = _agent_message(
            "Fulfillment in progress on another worker; poll tasks/get.",
            {META_STATUS: "payment-completed", META_RECEIPTS: receipts},
        )
        task = _task_dict(task_id=task_id, state="working", message=msg)
        stored.update(task)
        stored["receipts"] = receipts
        if not _persist_task(task_id, stored):
            return _jsonrpc_error(
                req_id,
                JSONRPC_INTERNAL_ERROR,
                "task persistence unavailable",
                {"taskId": task_id},
            )
        return _jsonrpc_result(req_id, _client_task_view(stored))

    out: dict[str, Any] | None = None
    try:
        te0 = time.perf_counter()
        deliverable = await binding.execute(skill_input)
        x402_latency.record_span("a2a", "fulfillment_execute", te0)
        if (
            stored.get("settle_after_fulfillment")
            and binding.settle_payment is not None
        ):
            settle_result = await binding.settle_payment(signature, header)
            if not settle_result.get("payment_settled"):
                msg = _agent_message(
                    "Open-data fetch succeeded but settlement failed; payment not charged.",
                    {
                        META_STATUS: "payment-failed",
                        META_ERROR: "SETTLEMENT_FAILED",
                        META_RECEIPTS: receipts,
                    },
                )
                task = _task_dict(task_id=task_id, state="input-required", message=msg)
                stored.update(task)
                stored["receipts"] = receipts
                if not _persist_task(task_id, stored):
                    out = _jsonrpc_error(
                        req_id,
                        JSONRPC_INTERNAL_ERROR,
                        "task persistence unavailable",
                        {"taskId": task_id},
                    )
                else:
                    out = _jsonrpc_result(req_id, _client_task_view(stored))
                return out
            settlement = settle_result.get("settlement") or {}
            settle_receipt = _settlement_receipt(settlement, network=network)
            receipts = list(stored.get("receipts") or []) + [settle_receipt]
            if binding.record_revenue:
                binding.record_revenue(settlement, stored.get("input") or {})
        msg = _agent_message(
            "Payment completed. Skill result attached as artifact.",
            {
                META_STATUS: "payment-completed",
                META_RECEIPTS: receipts,
            },
        )
        task = _task_dict(
            task_id=task_id,
            state="completed",
            message=msg,
            artifacts=[_artifact_from_result(deliverable)],
        )
        stored.update(task)
        stored["receipts"] = receipts
        stored["fulfillment_done"] = True
        if not _persist_task(task_id, stored):
            out = _jsonrpc_error(
                req_id,
                JSONRPC_INTERNAL_ERROR,
                "task persistence unavailable",
                {"taskId": task_id},
            )
        else:
            out = _jsonrpc_result(req_id, _client_task_view(stored))
    except Exception:  # noqa: BLE001
        log.warning("a2a skill execution failed", exc_info=True)
        status = (
            "Upstream data unavailable; payment was not charged."
            if stored.get("settle_after_fulfillment")
            else "Payment settled but skill execution failed."
        )
        msg = _agent_message(
            status,
            {
                META_STATUS: (
                    "payment-failed"
                    if stored.get("settle_after_fulfillment")
                    else "payment-completed"
                ),
                META_RECEIPTS: receipts,
            },
        )
        task = _task_dict(
            task_id=task_id,
            state="failed" if stored.get("settle_after_fulfillment") else "failed",
            message=msg,
        )
        stored.update(task)
        stored["receipts"] = receipts
        if not _persist_task(task_id, stored):
            out = _jsonrpc_error(
                req_id,
                JSONRPC_INTERNAL_ERROR,
                "task persistence unavailable",
                {"taskId": task_id},
            )
        else:
            out = _jsonrpc_result(req_id, _client_task_view(stored))
    finally:
        a2a_fulfillment_lock.release(task_id)

    assert out is not None
    return out


def _tasks_get(
    req_id: Any,
    params: dict[str, Any],
    *,
    headers: Mapping[str, str] | Headers | None,
) -> dict[str, Any]:
    task_id = params.get("id") or params.get("taskId")
    stored = _get_task_record(task_id) if task_id else None
    if not task_id or stored is None:
        return _jsonrpc_error(
            req_id,
            JSONRPC_TASK_NOT_FOUND,
            "task not found",
            {"taskId": task_id},
        )
    cap = _capability_from_task_ops(headers, params)
    cid = _client_id_from_task_ops(headers, params)
    reason = _authorize_task_access(stored, capability=cap, client_id=cid)
    if reason:
        return _jsonrpc_error(
            req_id,
            JSONRPC_FORBIDDEN,
            reason,
            {"taskId": task_id, "detail": reason},
        )
    return _jsonrpc_result(req_id, _client_task_view(stored))


def _tasks_cancel(
    req_id: Any,
    params: dict[str, Any],
    *,
    headers: Mapping[str, str] | Headers | None,
) -> dict[str, Any]:
    task_id = params.get("id") or params.get("taskId")
    stored = _get_task_record(task_id) if task_id else None
    if not task_id or stored is None:
        return _jsonrpc_error(
            req_id,
            JSONRPC_TASK_NOT_FOUND,
            "task not found",
            {"taskId": task_id},
        )
    cap = _capability_from_task_ops(headers, params)
    cid = _client_id_from_task_ops(headers, params)
    reason = _authorize_task_access(stored, capability=cap, client_id=cid)
    if reason:
        return _jsonrpc_error(
            req_id,
            JSONRPC_FORBIDDEN,
            reason,
            {"taskId": task_id, "detail": reason},
        )
    state = (stored.get("status") or {}).get("state")
    if state in {"completed", "failed", "canceled"}:
        return _jsonrpc_error(req_id, -32002, "task not cancelable")
    msg = _agent_message("Task canceled by client.", {})
    task = _task_dict(task_id=task_id, state="canceled", message=msg)
    stored.update(task)
    if not _persist_task(task_id, stored):
        return _jsonrpc_error(
            req_id,
            JSONRPC_INTERNAL_ERROR,
            "task persistence unavailable",
            {"taskId": task_id},
        )
    return _jsonrpc_result(req_id, _client_task_view(stored))


def extension_activation_response_headers(requested: str | None) -> dict[str, str]:
    """Echo x402-a2a extension when client activates it."""
    headers: dict[str, str] = {}
    if not requested:
        return headers
    for uri in A2A_X402_EXTENSION_URIS:
        if uri in requested:
            headers["X-A2A-Extensions"] = uri
            break
    return headers
