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


def _use_cdp(network: str | None) -> bool:
    """CDP facilitator is used when creds are set and the network needs it
    (Base mainnet etc.; the free x402.org facilitator only settles Base Sepolia)."""
    if not (settings.cdp_api_key_id and settings.cdp_api_key_secret):
        return False
    cdp_nets = {n.strip() for n in settings.cdp_networks.split(",") if n.strip()}
    return bool(network) and network in cdp_nets


def _facilitator_client(network: str | None = None):
    from x402.http import HTTPFacilitatorClient

    if _use_cdp(network):
        from app.cdp_auth import build_cdp_create_headers

        create_headers = build_cdp_create_headers(
            settings.cdp_api_key_id,
            settings.cdp_api_key_secret,
            settings.cdp_facilitator_url,
        )
        # dict-form config so the SDK wraps create_headers as an AuthProvider.
        return HTTPFacilitatorClient(
            {"url": settings.cdp_facilitator_url, "create_headers": create_headers}
        )

    from x402.http import FacilitatorConfig

    return HTTPFacilitatorClient(
        FacilitatorConfig(url=settings.x402_facilitator_url)
    )


def _probe_http_client():
    """x402HTTPClient for parsing 402 responses (no wallet required)."""
    from x402 import x402Client
    from x402.http import x402HTTPClient

    return x402HTTPClient(x402Client())


def _register_server_schemes(server) -> list[str]:
    """Register every settlement scheme we support. EVM always; Solana (SVM) when
    the `x402[svm]` extra is installed. Returns the registered network patterns."""
    from x402.mechanisms.evm.exact import ExactEvmServerScheme

    server.register("eip155:*", ExactEvmServerScheme())
    registered = ["eip155:*"]
    try:
        from x402.mechanisms.svm.exact import ExactSvmServerScheme

        server.register("solana:*", ExactSvmServerScheme())
        registered.append("solana:*")
    except ImportError:
        pass  # svm extra not installed; EVM-only, no marketing/code contradiction
    return registered


def svm_available() -> bool:
    try:
        import x402.mechanisms.svm.exact  # noqa: F401

        return True
    except ImportError:
        return False


def _resource_server(network: str | None = None):
    from x402 import x402ResourceServer

    facilitator = _facilitator_client(network)
    server = x402ResourceServer(facilitator)
    _register_server_schemes(server)
    server.initialize()
    return server


def _facilitator_url_for(network: str | None) -> str:
    return (
        settings.cdp_facilitator_url
        if _use_cdp(network)
        else settings.x402_facilitator_url
    )


def _network_of(requirements: Any) -> str | None:
    """Extract the CAIP-2 network from a decoded requirements dict/object."""
    if isinstance(requirements, dict):
        return requirements.get("network")
    return getattr(requirements, "network", None)


def _decode_payment_inputs(
    payment_signature: str,
    payment_required: str,
) -> tuple[Any, Any]:
    """Decode buyer signature + served challenge into SDK models.

    verify_payment/settle_payment require PaymentPayload + PaymentRequirements
    models (not raw dicts), so parse via the SDK decode helpers.
    """
    import base64

    from x402.http import (
        decode_payment_required_header,
        decode_payment_signature_header,
    )
    from x402.schemas import PaymentPayload, PaymentRequirements

    # Payment requirements: prefer the full PAYMENT-REQUIRED header (has accepts),
    # else treat the payload as a single bare requirement object.
    try:
        pr = decode_payment_required_header(payment_required)
        accepts = list(getattr(pr, "accepts", []) or [])
        if not accepts:
            raise ValueError("no accepts")
        requirements = accepts[0]
    except Exception:  # noqa: BLE001 — fall back to bare requirement dict
        raw = json.loads(base64.b64decode(payment_required).decode("utf-8"))
        bare = (raw.get("accepts") or [raw])[0]
        requirements = PaymentRequirements.model_validate(bare)

    # Buyer's signed payload (PAYMENT-SIGNATURE header value).
    try:
        payload = decode_payment_signature_header(payment_signature)
    except Exception:  # noqa: BLE001 — fall back to raw base64 json
        raw = json.loads(base64.b64decode(payment_signature).decode("utf-8"))
        payload = PaymentPayload.model_validate(raw)

    return payload, requirements


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


def parse_amount_atomic(value: Any) -> int | None:
    """Parse a Bazaar `accepts[].amount` into atomic units (1e6 = 1 USDC).

    Catalog items normally advertise atomic-unit integers, but some now send
    decimal-USDC strings (e.g. "0.016"); treat any value with a fractional
    part as decimal USDC. Returns None for unparseable values so callers can
    skip the entry instead of dropping the whole catalog.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        num = float(text)
    except (TypeError, ValueError):
        return None
    if num < 0:
        return None
    if "." in text or "e" in text.lower():
        return int(round(num * 1_000_000))
    return int(num)


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
            if any(
                amount is not None and amount <= max_atomic
                for r in i.get("accepts", [])
                for amount in (parse_amount_atomic(r.get("amount", 0)),)
            )
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


def _build_x402_client(preferred_network: str | None = None):
    from app.keyprovider import get_key_provider

    evm_key = get_key_provider().get_private_key()
    svm_key = settings.svm_private_key
    if not evm_key and not svm_key:
        raise ValueError(
            "EVM_PRIVATE_KEY (or SVM_PRIVATE_KEY) is required for pay_and_fetch. "
            "Set it in .env or use get_payment_requirements for probe-only flows."
        )

    from x402 import prefer_network, x402Client

    client = x402Client()

    if evm_key:
        from eth_account import Account
        from x402.mechanisms.evm import EthAccountSigner
        from x402.mechanisms.evm.exact.register import register_exact_evm_client

        register_exact_evm_client(client, EthAccountSigner(Account.from_key(evm_key)))

    if svm_key:
        try:
            from solders.keypair import Keypair
            from x402.mechanisms.svm.exact.register import register_exact_svm_client
            from x402.mechanisms.svm.signers import KeypairSigner

            register_exact_svm_client(
                client, KeypairSigner(Keypair.from_base58_string(svm_key))
            )
        except ImportError:
            pass  # svm extra not installed; EVM-only buyer

    network = preferred_network or settings.x402_default_network
    if network:
        client.register_policy(prefer_network(network))

    return client


async def pay_and_fetch(params: PayAndFetchInput) -> dict[str, Any]:
    """Execute x402 paid HTTP request via x402HttpxClient SDK."""
    from x402.http import x402HTTPClient
    from x402.http.clients import x402HttpxClient

    client = _build_x402_client(params.preferred_network)
    http_client = x402HTTPClient(client)

    # Client-level timeout applies to the paid retry too (mainnet settle is slow).
    async with x402HttpxClient(client, timeout=settings.x402_http_timeout) as http:
        response = await http.request(
            params.method.upper(),
            str(params.url),
            headers=params.headers,
            content=params.body,
        )
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

        # A PAYMENT-RESPONSE header proves settlement was *attempted*; only
        # SettleResponse.success proves funds actually moved on-chain.
        settled_ok = settle is not None and getattr(settle, "success", None) is True

        return {
            "status_code": response.status_code,
            "body": response.text[:8000],
            "payment_settled": settled_ok,
            "payment_settlement": settlement_dump,
            "settlement_parse_error": settle_error,
            "url": str(params.url),
            "sdk": "x402HttpxClient",
        }


def _build_discovery_extension(
    method: str,
    input_example: dict[str, Any] | None,
    output_example: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the Bazaar discovery extension dict ({"bazaar": {info, schema}}).

    Buyer x402 clients copy PaymentRequired.extensions verbatim into the signed
    PaymentPayload; at settle time the CDP facilitator's extract_discovery_info
    reads it to catalog the endpoint. The SDK's declare_discovery_extension
    omits the HTTP method (normally injected per-request by
    bazaar_resource_server_extension), but we serve a pre-encoded header, so
    inject it here — without it, `info` fails validation against its own
    `schema` and the facilitator catalogs nothing.
    """
    from x402.extensions.bazaar import OutputConfig, declare_discovery_extension
    from x402.extensions.bazaar.types import BAZAAR, is_body_method

    method = method.upper()
    extension = declare_discovery_extension(
        input=input_example,
        body_type="json" if is_body_method(method) else None,
        output=OutputConfig(example=output_example)
        if output_example is not None
        else None,
    )
    extension[BAZAAR.key]["info"]["input"]["method"] = method
    return extension


def _build_resource_info(params: BuildSellerRequirementsInput) -> Any:
    """ResourceInfo (url/description/mime + Bazaar service metadata) for a 402."""
    from x402.schemas import ResourceInfo

    tags = [
        t.strip()[:32] for t in settings.bazaar_service_tags.split(",") if t.strip()
    ][:5]
    return ResourceInfo(
        url=str(params.resource_url),
        description=params.description,
        mime_type=params.mime_type,
        service_name=settings.bazaar_service_name.strip()[:32] or None,
        tags=tags or None,
    )


def build_seller_requirements(params: BuildSellerRequirementsInput) -> dict[str, Any]:
    pay_to = params.pay_to or settings.x402_pay_to_address
    if not pay_to:
        raise ValueError(
            "pay_to address required. Pass pay_to or set X402_PAY_TO_ADDRESS."
        )
    # Only the `exact` scheme is registered (ExactEvmServerScheme); reject others
    # up front rather than raising an opaque SchemeNotFoundError from the SDK.
    if params.scheme != "exact":
        raise ValueError(
            f"unsupported scheme '{params.scheme}'; only 'exact' is supported"
        )

    from x402 import ResourceConfig, x402ResourceServer
    from x402.http import encode_payment_required_header
    from x402.schemas import PaymentRequired

    facilitator = _facilitator_client(params.network)
    server = x402ResourceServer(facilitator)
    _register_server_schemes(server)
    server.initialize()

    config = ResourceConfig(
        scheme=params.scheme,
        network=params.network,
        pay_to=pay_to,
        price=params.price,
        description=params.description,
    )
    requirements = server.build_payment_requirements(config)

    # Bazaar discoverability: with a resource_url the challenge carries
    # ResourceInfo, and (unless opted out) the bazaar discovery extension —
    # without it a settled payment through the CDP facilitator catalogs nothing.
    resource_info = None
    extensions = None
    if params.resource_url:
        resource_info = _build_resource_info(params)
        discoverable = (
            params.discoverable
            if params.discoverable is not None
            else settings.bazaar_discoverable
        )
        if discoverable:
            extensions = _build_discovery_extension(
                params.discovery_method,
                params.discovery_input_example,
                params.discovery_output_example,
            )

    # Encode the ready-to-serve 402 challenge header (PAYMENT-REQUIRED) so an
    # HTTP endpoint can hand it to a buyer's x402 client verbatim.
    payment_required = PaymentRequired(
        x402_version=2,
        accepts=list(requirements),
        error=params.description,
        resource=resource_info,
        extensions=extensions,
    )
    payment_required_header = encode_payment_required_header(payment_required)

    return {
        "requirements": [
            r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in requirements
        ],
        "payment_required_header": payment_required_header,
        "network": params.network,
        "pay_to": pay_to,
        "price": params.price,
        "scheme": params.scheme,
        "resource": resource_info.model_dump() if resource_info else None,
        "discoverable": extensions is not None,
        "facilitator_url": _facilitator_url_for(params.network),
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
    network = _network_of(requirements)
    server = _resource_server(network)
    result = await server.verify_payment(payload, requirements)

    return {
        "is_valid": result.is_valid,
        "invalid_reason": getattr(result, "invalid_reason", None),
        "facilitator_url": _facilitator_url_for(network),
        "sdk": "x402ResourceServer.verify_payment",
    }


async def _verify_and_settle_payment(params: VerifyPaymentInput) -> dict[str, Any]:
    """Seller revenue path: verify then settle via x402ResourceServer + facilitator."""
    payload, requirements = _decode_payment_inputs(
        params.payment_signature, params.payment_required
    )
    network = _network_of(requirements)
    server = _resource_server(network)
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
        "facilitator_url": _facilitator_url_for(network),
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
    if not payment.get("payment_settled"):
        raise ValueError(
            "Tool credits payment did not settle on-chain: "
            f"{payment.get('settlement_error') or 'settlement unsuccessful'}"
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
    if not payment.get("payment_settled"):
        raise ValueError(
            "Pro tier payment did not settle on-chain: "
            f"{payment.get('settlement_error') or 'settlement unsuccessful'}"
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