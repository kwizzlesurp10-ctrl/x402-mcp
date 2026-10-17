"""A2A JSON-RPC endpoint (message/send, tasks/get, tasks/cancel) with x402-a2a payments."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from starlette.datastructures import Headers

from app.agent_surface import A2A_X402_EXTENSION_URI, A2A_X402_EXTENSION_URIS
from app.config import settings

log = logging.getLogger("x402")

# x402-a2a metadata keys (standalone flow).
META_STATUS = "x402.payment.status"
META_REQUIRED = "x402.payment.required"
META_PAYLOAD = "x402.payment.payload"
META_RECEIPTS = "x402.payment.receipts"
META_ERROR = "x402.payment.error"

JSONRPC_TASK_NOT_FOUND = -32001
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_METHOD_NOT_FOUND = -32601

_TASKS: dict[str, dict[str, Any]] = {}


def clear_task_store() -> None:
    """Test hook: drop in-memory A2A tasks."""
    _TASKS.clear()


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
    from app import diligence_pack, property_due_diligence_agent as pdd_agent, tx_decision
    from app.city_compliance import registry

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
            report = await mod.check_property(str(inp.get("address") or ""))
            if not isinstance(report, dict):
                report = {"result": report}
            out = dict(report)
            out.setdefault("city", city_code)
            out["payment_settled"] = True
            return out

        def _city_validate(inp: dict[str, Any]) -> str | None:
            addr = str(inp.get("address") or "").strip()
            if not addr or len(addr) > 120:
                return "address must be 1-120 chars"
            return None

        from app.city_compliance import gate as city_gate

        mod = registry.get_city(code)
        spec = mod.SPEC
        input_example = {"address": spec.sample_address}
        output_example = mod.discovery_output_example()
        pid = city_gate.product_id(spec)

        bindings[skill_id] = SkillBinding(
            skill_id=skill_id,
            product_id=pid,
            price_usdc=entry["price"],
            build_payment_header=lambda: city_gate.build_payment_required_header(
                spec,
                input_example=input_example,
                output_example=output_example,
            ),
            verify_and_settle=city_gate.verify_and_settle,
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


async def handle_jsonrpc(body: dict[str, Any], *, user_agent: str | None = None) -> dict[str, Any]:
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
        return await _message_send(req_id, params, user_agent=user_agent)
    if method == "tasks/get":
        return _tasks_get(req_id, params)
    if method == "tasks/cancel":
        return _tasks_cancel(req_id, params)
    return _jsonrpc_error(req_id, JSONRPC_METHOD_NOT_FOUND, "method not found")


async def _message_send(
    req_id: Any,
    params: dict[str, Any],
    *,
    user_agent: str | None,
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
        _TASKS[tid] = task
        return _jsonrpc_result(req_id, task)

    payload_obj = meta.get(META_PAYLOAD)
    if pay_status == "payment-submitted" or payload_obj is not None:
        if not task_id or task_id not in _TASKS:
            return _jsonrpc_error(
                req_id,
                JSONRPC_TASK_NOT_FOUND,
                "task not found",
                {"taskId": task_id},
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
        _TASKS[tid] = {**task, "skillId": skill_id, "input": skill_input}
        return _jsonrpc_result(req_id, task)

    if not settings.x402_pay_to_address:
        return _jsonrpc_error(req_id, -32004, "seller not configured")

    try:
        assert binding.build_payment_header is not None
        header = binding.build_payment_header()
        required_body = _payment_required_body(header)
    except Exception:  # noqa: BLE001
        log.warning("a2a: cannot build payment challenge skill=%s", skill_id, exc_info=True)
        return _jsonrpc_error(req_id, -32004, "challenge unavailable")

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
    _TASKS[tid] = {
        **task,
        "skillId": skill_id,
        "input": skill_input,
        "product_id": binding.product_id,
        "payment_required_header": header,
        "receipts": [],
        "binding": binding,
    }
    return _jsonrpc_result(req_id, task)


async def _continue_paid_task(
    req_id: Any,
    task_id: str,
    payload_obj: Any,
    *,
    user_agent: str | None,
) -> dict[str, Any]:
    stored = _TASKS[task_id]
    binding: SkillBinding = stored["binding"]
    header = stored["payment_required_header"]
    network = settings.x402_default_network

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
        return _jsonrpc_result(req_id, task)

    assert binding.verify_and_settle is not None
    result = await binding.verify_and_settle(signature, header)
    settlement = result.get("settlement") or {}
    receipt = _settlement_receipt(settlement, network=network)
    if not result.get("is_valid"):
        receipt["success"] = False
        receipt["errorReason"] = result.get("invalid_reason") or "invalid_signature"
    receipts = list(stored.get("receipts") or []) + [receipt]

    if not result.get("is_valid") or not result.get("payment_settled"):
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
        return _jsonrpc_result(req_id, task)

    if binding.record_revenue:
        binding.record_revenue(settlement, stored.get("input") or {})

    skill_input = stored.get("input") or {}
    try:
        deliverable = await binding.execute(skill_input)
    except Exception as exc:  # noqa: BLE001
        log.warning("a2a skill execution failed after settle", exc_info=True)
        msg = _agent_message(
            "Payment settled but skill execution failed.",
            {
                META_STATUS: "payment-completed",
                META_RECEIPTS: receipts,
            },
        )
        task = _task_dict(task_id=task_id, state="failed", message=msg)
        stored.update(task)
        stored["receipts"] = receipts
        return _jsonrpc_result(req_id, task)

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
    return _jsonrpc_result(req_id, task)


def _tasks_get(req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params.get("id") or params.get("taskId")
    if not task_id or task_id not in _TASKS:
        return _jsonrpc_error(
            req_id,
            JSONRPC_TASK_NOT_FOUND,
            "task not found",
            {"taskId": task_id},
        )
    stored = _TASKS[task_id]
    # Return public task shape only (omit binding/header).
    task = {k: v for k, v in stored.items() if k not in {"binding", "payment_required_header", "input", "product_id"}}
    if "kind" not in task:
        task = _task_dict(
            task_id=task_id,
            state=stored.get("status", {}).get("state", "unknown"),
            message=(stored.get("status") or {}).get("message"),
            artifacts=stored.get("artifacts"),
        )
    return _jsonrpc_result(req_id, task)


def _tasks_cancel(req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params.get("id") or params.get("taskId")
    if not task_id or task_id not in _TASKS:
        return _jsonrpc_error(
            req_id,
            JSONRPC_TASK_NOT_FOUND,
            "task not found",
            {"taskId": task_id},
        )
    stored = _TASKS[task_id]
    state = (stored.get("status") or {}).get("state")
    if state in {"completed", "failed", "canceled"}:
        return _jsonrpc_error(req_id, -32002, "task not cancelable")
    msg = _agent_message("Task canceled by client.", {})
    task = _task_dict(task_id=task_id, state="canceled", message=msg)
    stored.update(task)
    return _jsonrpc_result(req_id, task)


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
