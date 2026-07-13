"""x402 protocol operations — all flows use the official x402 Python SDK."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.commerce import quota_store
from app.config import settings
from app.models import (
    BuildSellerRequirementsInput,
    DiscoverServicesInput,
    GetPaymentRequirementsInput,
    PayAndFetchInput,
    SupportedNetworksOutput,
    VerifyPaymentInput,
)


def _facilitator_client():
    from x402.http import FacilitatorConfig, HTTPFacilitatorClient

    return HTTPFacilitatorClient(
        FacilitatorConfig(url=settings.x402_facilitator_url)
    )


def _probe_http_client():
    """x402HTTPClient for parsing 402 responses (no wallet required)."""
    from x402 import x402Client
    from x402.http import x402HTTPClient

    return x402HTTPClient(x402Client())


def _resource_server():
    from x402 import x402ResourceServer
    from x402.mechanisms.evm.exact import ExactEvmServerScheme

    facilitator = _facilitator_client()
    server = x402ResourceServer(facilitator)
    server.register("eip155:*", ExactEvmServerScheme())
    server.initialize()
    return server


def _decode_payment_inputs(
    payment_signature: str,
    payment_required: str,
) -> tuple[Any, Any]:
    """Decode base64 headers into typed SDK models.

    x402ResourceServer.verify_payment requires PaymentPayload/PaymentRequirements
    models (it reads attributes like .network); raw dicts crash it.
    """
    import base64

    from x402 import parse_payment_payload, parse_payment_required

    try:
        requirements_raw = json.loads(
            base64.b64decode(payment_required).decode("utf-8")
        )
        required = parse_payment_required(requirements_raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid payment_required payload: {exc}") from exc

    if not required.accepts:
        raise ValueError("No payment requirements found in payment_required payload")

    try:
        payload_raw = json.loads(
            base64.b64decode(payment_signature).decode("utf-8")
        )
        payload = parse_payment_payload(payload_raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid payment_signature payload: {exc}") from exc

    return payload, required.accepts[0]


def _sdk_parse_payment_required(
    http_client: Any,
    response: httpx.Response,
) -> tuple[Any | None, str | None]:
    """Parse 402 body/headers via public x402HTTPClient SDK helpers."""
    from x402.http import HTTP_STATUS_PAYMENT_REQUIRED

    if response.status_code != HTTP_STATUS_PAYMENT_REQUIRED:
        return None, None

    body_data = None
    try:
        body_data = response.json()
    except (json.JSONDecodeError, ValueError):
        body_data = response.content or None

    try:
        return http_client.get_payment_required_response(
            response.headers.get, body_data
        ), None
    except ValueError as exc:
        return None, str(exc)


def get_supported_networks() -> SupportedNetworksOutput:
    facilitator = _facilitator_client()
    supported = facilitator.get_supported()
    return SupportedNetworksOutput(
        networks=[
            {"id": "eip155:8453", "name": "Base Mainnet", "asset": "USDC"},
            {"id": "eip155:84532", "name": "Base Sepolia (testnet)", "asset": "USDC"},
            {"id": "eip155:137", "name": "Polygon", "asset": "USDC"},
            {"id": "solana:mainnet", "name": "Solana Mainnet", "asset": "USDC"},
        ],
        facilitators=[
            {
                "name": "configured",
                "url": settings.x402_facilitator_url,
                "auth": "optional",
            },
        ],
        default_network=settings.x402_default_network,
        headers={
            "PAYMENT-REQUIRED": "Base64 payment requirements on HTTP 402",
            "PAYMENT-SIGNATURE": "Base64 signed payment payload on retry",
            "PAYMENT-RESPONSE": "Base64 settlement details on HTTP 200",
        },
        facilitator_supported=supported.model_dump(),
    )


async def discover_services(params: DiscoverServicesInput) -> dict[str, Any]:
    """Query Bazaar via public facilitator.get_supported + httpx discovery fetch."""
    facilitator = _facilitator_client()
    supported = facilitator.get_supported()

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(
            settings.cdp_discovery_url,
            params={"type": "http", "limit": params.limit},
        )
        response.raise_for_status()
        payload = response.json()

    items = payload.get("items", payload.get("resources", []))
    if params.query:
        needle = params.query.lower()
        items = [i for i in items if needle in json.dumps(i).lower()]

    if params.max_price_usdc is not None:
        max_atomic = int(params.max_price_usdc * 1_000_000)
        items = [
            i
            for i in items
            if any(int(r.get("amount", 0)) <= max_atomic for r in i.get("accepts", []))
        ]

    return {
        "count": len(items),
        "services": items[: params.limit],
        "discovery_url": settings.cdp_discovery_url,
        "facilitator_url": settings.x402_facilitator_url,
        "facilitator_supported": supported.model_dump(),
        "sdk": "x402.HTTPFacilitatorClient.get_supported + httpx.AsyncClient",
    }


async def get_payment_requirements(
    params: GetPaymentRequirementsInput,
) -> dict[str, Any]:
    """Probe URL; x402 parsing exclusively via public x402HTTPClient SDK helpers."""
    from x402.http import HTTP_STATUS_PAYMENT_REQUIRED, detect_payment_required_version

    http_client = _probe_http_client()

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.request(
            params.method.upper(),
            str(params.url),
            headers=params.headers,
        )
        await response.aread()

    version = None
    try:
        version = detect_payment_required_version(
            dict(response.headers), response.content
        )
    except ValueError:
        version = None

    payment_required_model, decode_error = _sdk_parse_payment_required(
        http_client, response
    )
    payment_required_b64 = response.headers.get("PAYMENT-REQUIRED")
    decoded = (
        payment_required_model.model_dump()
        if payment_required_model is not None
        else None
    )

    return {
        "status_code": response.status_code,
        "payment_required": payment_required_b64 is not None or payment_required_model is not None,
        "payment_required_header": payment_required_b64,
        "payment_required_decoded": decoded,
        "protocol_version": version,
        "decode_error": decode_error,
        "response_preview": response.text[:500] if response.text else None,
        "sdk": "x402HTTPClient.get_payment_required_response + detect_payment_required_version",
        "note": (
            "HTTP 402 with PAYMENT-REQUIRED indicates x402 micropayment is required."
            if response.status_code == HTTP_STATUS_PAYMENT_REQUIRED
            else "Resource may not require x402 payment."
        ),
    }


def _build_x402_client(
    preferred_network: str | None = None,
    max_price_usdc: float | None = None,
):
    if not settings.evm_private_key:
        raise ValueError(
            "EVM_PRIVATE_KEY is required for pay_and_fetch. "
            "Set it in .env or use get_payment_requirements for probe-only flows."
        )

    from eth_account import Account
    from x402 import max_amount, prefer_network, x402Client
    from x402.mechanisms.evm import EthAccountSigner
    from x402.mechanisms.evm.exact.register import register_exact_evm_client

    client = x402Client()
    account = Account.from_key(settings.evm_private_key)
    register_exact_evm_client(client, EthAccountSigner(account))

    network = preferred_network or settings.x402_default_network
    if network:
        client.register_policy(prefer_network(network))

    if max_price_usdc is not None:
        client.register_policy(max_amount(int(max_price_usdc * 1_000_000)))

    return client


async def pay_and_fetch(params: PayAndFetchInput) -> dict[str, Any]:
    """Execute x402 paid HTTP request via x402HttpxClient SDK."""
    from x402 import NoMatchingRequirementsError
    from x402.http import x402HTTPClient
    from x402.http.clients import x402HttpxClient

    client = _build_x402_client(params.preferred_network, params.max_price_usdc)
    http_client = x402HTTPClient(client)

    async with x402HttpxClient(client) as http:
        try:
            response = await http.request(
                params.method.upper(),
                str(params.url),
                headers=params.headers,
                content=params.body,
            )
        except Exception as exc:
            # x402HttpxClient wraps selection errors in its own module-local
            # PaymentError (raised `from` the original) — unwrap via __cause__
            # to detect a max_price_usdc refusal regardless of wrapper type.
            if not isinstance(exc, NoMatchingRequirementsError) and not isinstance(
                exc.__cause__, NoMatchingRequirementsError
            ):
                raise
            raise ValueError(
                "payment refused: no accepted payment option within "
                f"max_price_usdc={params.max_price_usdc} for {params.url} ({exc})"
            ) from exc
        await response.aread()

        settle = None
        settle_error = None
        if response.is_success:
            try:
                settle = http_client.get_payment_settle_response(
                    lambda name: response.headers.get(name)
                )
            except ValueError as exc:
                settle_error = str(exc)
                settle = None

        settlement_dump = None
        if settle is not None:
            settlement_dump = settle.model_dump()

        return {
            "status_code": response.status_code,
            "body": response.text[:8000],
            "payment_settled": settlement_dump is not None,
            "payment_settlement": settlement_dump,
            "settlement_parse_error": settle_error,
            "url": str(params.url),
            "sdk": "x402HttpxClient",
        }


def build_seller_requirements(params: BuildSellerRequirementsInput) -> dict[str, Any]:
    pay_to = params.pay_to or settings.x402_pay_to_address
    if not pay_to:
        raise ValueError(
            "pay_to address required. Pass pay_to or set X402_PAY_TO_ADDRESS."
        )

    from x402 import ResourceConfig, x402ResourceServer
    from x402.mechanisms.evm.exact import ExactEvmServerScheme

    facilitator = _facilitator_client()
    server = x402ResourceServer(facilitator)
    server.register("eip155:*", ExactEvmServerScheme())
    server.initialize()

    config = ResourceConfig(
        scheme=params.scheme,
        network=params.network,
        pay_to=pay_to,
        price=params.price,
        description=params.description,
    )
    requirements = server.build_payment_requirements(config)

    return {
        "requirements": [
            r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in requirements
        ],
        "network": params.network,
        "pay_to": pay_to,
        "price": params.price,
        "scheme": params.scheme,
        "facilitator_url": settings.x402_facilitator_url,
        "sdk": "x402ResourceServer.build_payment_requirements",
    }


def build_pro_upgrade_requirements(agent_id: str) -> dict[str, Any]:
    """Build x402 payment requirements to purchase Pro tier (revenue path)."""
    pay_to = settings.x402_pay_to_address
    if not pay_to:
        raise ValueError("X402_PAY_TO_ADDRESS required to collect pro tier payments.")

    result = build_seller_requirements(
        BuildSellerRequirementsInput(
            network=settings.x402_default_network,
            pay_to=pay_to,
            price=settings.pro_tier_price,
            description=f"x402 MCP Pro tier for agent {agent_id}",
        )
    )
    result["purpose"] = "pro_tier_upgrade"
    result["agent_id"] = agent_id
    result["pro_benefits"] = {
        "monthly_quota": settings.pro_tier_monthly_quota,
        "rate_limit_per_min": settings.pro_tier_rate_limit_per_min,
    }
    return result


async def verify_payment_payload(params: VerifyPaymentInput) -> dict[str, Any]:
    payload, requirements = _decode_payment_inputs(
        params.payment_signature, params.payment_required
    )
    server = _resource_server()
    result = await server.verify_payment(payload, requirements)

    return {
        "is_valid": result.is_valid,
        "invalid_reason": getattr(result, "invalid_reason", None),
        "facilitator_url": settings.x402_facilitator_url,
        "sdk": "x402ResourceServer.verify_payment",
    }


async def _verify_and_settle_payment(params: VerifyPaymentInput) -> dict[str, Any]:
    """Seller revenue path: verify then settle via x402ResourceServer + facilitator."""
    payload, requirements = _decode_payment_inputs(
        params.payment_signature, params.payment_required
    )
    server = _resource_server()
    verify_result = await server.verify_payment(payload, requirements)

    settlement = None
    settlement_error = None
    if verify_result.is_valid:
        try:
            settle_result = await server.settle_payment(payload, requirements)
            settlement = settle_result.model_dump()
        except Exception as exc:
            settlement_error = str(exc)

    return {
        "is_valid": verify_result.is_valid,
        "invalid_reason": getattr(verify_result, "invalid_reason", None),
        "settlement": settlement,
        "settlement_error": settlement_error,
        "payment_settled": settlement is not None and settlement.get("success") is True,
        "facilitator_url": settings.x402_facilitator_url,
        "sdk": "x402ResourceServer.verify_payment + settle_payment",
    }


def build_tool_credits_requirements(agent_id: str, credits: int) -> dict[str, Any]:
    """Build x402 payment requirements to purchase per-use MCP tool credits."""
    pay_to = settings.x402_pay_to_address
    if not pay_to:
        raise ValueError("X402_PAY_TO_ADDRESS required to collect tool credit payments.")

    result = build_seller_requirements(
        BuildSellerRequirementsInput(
            network=settings.x402_default_network,
            pay_to=pay_to,
            price=settings.tool_credit_pack_price,
            description=f"x402 MCP tool credits ({credits}) for agent {agent_id}",
        )
    )
    result["purpose"] = "tool_credits"
    result["agent_id"] = agent_id
    result["credits"] = credits
    return result


async def purchase_tool_credits(
    payment_signature: str,
    payment_required: str,
    agent_id: str,
    credits: int,
) -> dict[str, Any]:
    """Verify + settle x402 payment, then credit agent balance (per-use revenue)."""
    payment = await _verify_and_settle_payment(
        VerifyPaymentInput(
            payment_signature=payment_signature,
            payment_required=payment_required,
        )
    )
    if not payment["is_valid"]:
        raise ValueError(
            f"Tool credits payment invalid: {payment.get('invalid_reason', 'unknown')}"
        )

    balance = quota_store.add_credits(agent_id, credits)
    snapshot = quota_store.peek(agent_id)

    return {
        "credited": True,
        "agent_id": agent_id,
        "credits_purchased": credits,
        "tool_credits_remaining": balance,
        "tier": snapshot.tier,
        "payment_settled": payment["payment_settled"],
        "verification": payment,
    }


async def activate_pro_tier(
    payment_signature: str,
    payment_required: str,
    agent_id: str,
) -> dict[str, Any]:
    """Verify + settle x402 pro-tier payment and unlock pro quota."""
    payment = await _verify_and_settle_payment(
        VerifyPaymentInput(
            payment_signature=payment_signature,
            payment_required=payment_required,
        )
    )
    if not payment["is_valid"]:
        raise ValueError(
            f"Pro tier payment invalid: {payment.get('invalid_reason', 'unknown')}"
        )

    quota_store.activate_pro_tier(agent_id)
    snapshot = quota_store.peek(agent_id)

    return {
        "activated": True,
        "agent_id": agent_id,
        "tier": snapshot.tier,
        "pro_quota": settings.pro_tier_monthly_quota,
        "payment_settled": payment["payment_settled"],
        "verification": payment,
    }