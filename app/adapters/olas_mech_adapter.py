"""Olas (Autonolas) Mech Protocol Task Adapter.

Bridges autonomous on-chain Mech requests into x402-mcp's high-value diligence
and civic intelligence tasks, computing cryptographic deliverable hashes for
on-chain bounty settlement.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.diligence_pack import DiligencePackRequest, PropertyQuery, build_pack
from app.city_compliance import registry

log = logging.getLogger("x402.olas_mech")


class OlasMechAdapter:
    """Adapter executing Olas Mech on-chain agent tasks."""

    SUPPORTED_TOOLS = (
        "us-rental-diligence",
        "us-city-property-check",
        "base-tx-decision",
        "base-finality-check",
    )

    @classmethod
    def get_supported_tools(cls) -> list[dict[str, Any]]:
        """List of tools advertised to Olas Mech Marketplace registries."""
        return [
            {
                "name": "us-rental-diligence",
                "description": "Screen up to 5 US rental addresses across municipal open-data portals for code violations, licensing, and condemnation.",
                "pricing_usdc": 1.50,
                "input_schema": {
                    "properties": "list of {city_code, address}",
                    "include_base_pulse_context": "bool (optional)",
                },
            },
            {
                "name": "us-city-property-check",
                "description": "Address-level housing compliance and code violation lookup across 14+ US jurisdictions.",
                "pricing_usdc": 0.01,
                "input_schema": {
                    "city_code": "mn|sea|nyc|chi|den|sf|lax|bos|phi|orl|nola|moco|gain|kc",
                    "address": "street address string",
                },
            },
            {
                "name": "base-tx-decision",
                "description": "Live Base RPC congestion, EIP-1559 fee recommendation, and execution window guidance.",
                "pricing_usdc": 0.01,
                "input_schema": {
                    "gas": "usdc|eth|erc20|x402 (optional)",
                    "urgency": "now|soon|flexible (optional)",
                },
            },
            {
                "name": "base-finality-check",
                "description": "L1/L2 safe and finalized block tag verification for Base mainnet transactions.",
                "pricing_usdc": 0.01,
                "input_schema": {
                    "tx": "0x-prefixed 32-byte transaction hash",
                },
            },
        ]

    @classmethod
    async def execute_task(cls, request_data: dict[str, Any]) -> dict[str, Any]:
        """Execute a task received from an Olas Mech consumer agent.

        Expected request_data:
            {
                "tool": "us-rental-diligence",
                "params": { ... },  # or top-level params
                "task_id": "0x..."  # optional on-chain task id
            }
        """
        tool = request_data.get("tool") or "us-rental-diligence"
        params = request_data.get("params") or request_data
        task_id = request_data.get("task_id") or request_data.get("requestId")

        start_time = datetime.now(UTC)

        try:
            if tool == "us-rental-diligence":
                properties_raw = params.get("properties") or []
                if not properties_raw and "address" in params:
                    city_code = params.get("city_code") or "mn"
                    properties_raw = [{"city_code": city_code, "address": params["address"]}]

                if not properties_raw:
                    # Provide default sample if none passed
                    properties_raw = [{"city_code": "mn", "address": "1700 Penn Ave N"}]

                parsed_props = [
                    PropertyQuery(city_code=p["city_code"], address=p["address"])
                    for p in properties_raw
                ]
                diligence_req = DiligencePackRequest(
                    properties=parsed_props,
                    include_base_pulse_context=bool(params.get("include_base_pulse_context", False)),
                    idempotency_key=str(task_id or ""),
                )
                result = await build_pack(diligence_req, payment_settled=True)
                cost_usdc = 1.50

            elif tool in ("us-city-property-check", "property-check"):
                city_code = params.get("city_code") or "mn"
                address = params.get("address") or "1700 Penn Ave N"
                mod = registry.get_city(city_code)
                report = await mod.check_property(address)
                result = {
                    "tool": "us-city-property-check",
                    "city_code": city_code,
                    "address": address,
                    "report": report,
                }
                cost_usdc = 0.01

            elif tool == "base-tx-decision":
                from app import tx_decision
                gas = params.get("gas", "usdc")
                urgency = params.get("urgency", "flexible")
                decision = await tx_decision.get_tx_decision(gas=gas, urgency=urgency)
                result = decision
                cost_usdc = 0.01

            elif tool == "base-finality-check":
                from app import finality_check
                tx_hash = params.get("tx") or ""
                check = await finality_check.get_finality_check(tx=tx_hash)
                result = check
                cost_usdc = 0.01

            else:
                return {
                    "status": "error",
                    "error": f"unsupported_tool: {tool}",
                    "supported_tools": list(cls.SUPPORTED_TOOLS),
                }

            # Serialize and compute hash for on-chain settlement deliverable
            serialized = json.dumps(result, sort_keys=True, default=str)
            deliverable_hash = "0x" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()

            return {
                "status": "success",
                "tool": tool,
                "task_id": task_id,
                "deliverable_hash": deliverable_hash,
                "cost_usdc": cost_usdc,
                "executed_at": start_time.isoformat(),
                "result": result,
            }

        except Exception as exc:
            log.error("Mech task execution failed tool=%s: %s", tool, exc, exc_info=True)
            return {
                "status": "error",
                "tool": tool,
                "task_id": task_id,
                "error": type(exc).__name__,
                "detail": str(exc),
            }
