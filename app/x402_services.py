"""x402 protocol operations — all flows use the official x402 Python SDK."""

from __future__ import annotations

import json
import logging
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

logger = logging.getLogger("x402")

# The CDP Facilitator rejects BOTH verify and settle when a resource description
# exceeds this many characters, which would silently break discovery AND revenue.
# We clamp centrally so no caller (e.g. a composite listing whose description
# embeds a user-supplied topic) can ever emit an uncatalogable / unsettleable 402.
CDP_MAX_DESCRIPTION_CHARS = 500


def _clamp_description(description: str) -> str:
    if len(description) <= CDP_MAX_DESCRIPTION_CHARS:
        return description
    clamped = description[: CDP_MAX_DESCRIPTION_CHARS - 3].rstrip() + "..."
    logger.warning(
        "description of %d chars exceeds CDP limit %d; truncated for the served "
        "402 (CDP rejects verify+settle above the limit)",
        len(description),
        CDP_MAX_DESCRIPTION_CHARS,
    )
    return clamped


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

    return HTTPFacilitatorClient()


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
    try:
        server.initialize()
    except Exception as exc:
        logger.warning("Facilitator initialize skipped (unauthenticated/offline): %s", exc)
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

    # Buyer's signed payload (PAYMENT-SIGNATURE header value).
    try:
        payload = decode_payment_signature_header(payment_signature)
    except Exception:  # noqa: BLE001 — fall back to raw base64 json
        raw = json.loads(base64.b64decode(payment_signature).decode("utf-8"))
        payload = PaymentPayload.model_validate(raw)

    # Payment requirements: prefer the full PAYMENT-REQUIRED header (has accepts),
    # else treat the payload as a single bare requirement object.
    try:
        pr = decode_payment_required_header(payment_required)
        accepts = list(getattr(pr, "accepts", []) or [])
        if not accepts:
            raise ValueError("no accepts")
        
        # Match the requirement the buyer actually accepted
        accepted_net = getattr(payload.accepted, "network", None)
        accepted_asset = getattr(payload.accepted, "asset", None)
        matched = None
        for req in accepts:
            if getattr(req, "network", None) == accepted_net and getattr(req, "asset", None) == accepted_asset:
                matched = req
                break
        
        requirements = matched if matched else accepts[0]
    except Exception:  # noqa: BLE001 — fall back to bare requirement dict
        raw = json.loads(base64.b64decode(payment_required).decode("utf-8"))
        bare = (raw.get("accepts") or [raw])[0]
        requirements = PaymentRequirements.model_validate(bare)

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


def _build_x402_client(
    preferred_network: str | None = None,
    max_price_usdc: float | None = None,
):
    from app.keyprovider import get_key_provider

    evm_key = get_key_provider().get_private_key()
    svm_key = settings.svm_private_key
    if not evm_key and not svm_key:
        raise ValueError(
            "EVM_PRIVATE_KEY (or SVM_PRIVATE_KEY) is required for pay_and_fetch. "
            "Set it in .env or use get_payment_requirements for probe-only flows."
        )

    from x402 import max_amount, prefer_network, x402Client

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

    if max_price_usdc is not None:
        client.register_policy(max_amount(usdc_cap_atomic(max_price_usdc)))

    return client


def usdc_cap_atomic(max_price_usdc: float) -> int:
    """Buyer max_amount cap in USDC atomic units (6 decimals).

    Use round(), not truncating int(): ``int(0.01 * 1_000_000)`` is 9999 on
    some IEEE-754 platforms, which silently refuses a $0.01 (10000) city
    quote when the agent caps at list price.
    """
    return int(round(float(max_price_usdc) * 1_000_000))


# USDC (the only asset this repo prices in) has 6 decimals, which both
# ledger_writer._atomic and publisher.parse_price_usdc hardcode. The real
# figure is still looked up per asset below so a non-USDC settlement can never
# be recorded off by orders of magnitude.
DEFAULT_ASSET_DECIMALS = 6


def asset_decimals(network: str | None, asset: str | None) -> int:
    """Decimals for `asset` on `network`; USDC's 6 when it can't be resolved."""
    if not network or not asset:
        return DEFAULT_ASSET_DECIMALS
    network = str(network)
    try:
        if network.startswith("eip155:"):
            from x402.mechanisms.evm.utils import get_asset_info
        elif network.startswith("solana:"):
            from x402.mechanisms.svm.utils import get_asset_info
        else:
            return DEFAULT_ASSET_DECIMALS
        return int(get_asset_info(network, str(asset))["decimals"])
    except Exception:  # noqa: BLE001 — unregistered asset/import: fall back, never raise
        return DEFAULT_ASSET_DECIMALS


def atomic_to_units(
    amount_atomic: Any,
    network: str | None = None,
    asset: str | None = None,
) -> float | None:
    """Convert an on-wire atomic amount to a decimal figure, or None if unusable.

    Amounts cross the x402 wire as decimal *strings* of atomic units
    (`PaymentRequirements.amount`, `SettleResponse.amount`). Anything that
    isn't a non-negative integer is treated as absent rather than guessed at —
    a wrong number in a money ledger is worse than a missing one.
    """
    if amount_atomic is None or isinstance(amount_atomic, bool):
        return None
    try:
        atomic = int(str(amount_atomic).strip())
    except (TypeError, ValueError):
        return None
    if atomic < 0:
        return None
    return atomic / (10 ** asset_decimals(network, asset))


def signed_requirements_capture() -> tuple[dict[str, Any], Any]:
    """`(store, hook)` for x402Client.on_after_payment_creation.

    The amount a buyer is actually charged is only knowable from the payment
    requirements its client selects out of the 402 — `max_price_usdc` is a
    ceiling, not a price. Verified against the installed x402 2.14.0:
    `x402Client.on_after_payment_creation` (x402/client.py:125) fires with a
    `PaymentCreatedContext` carrying `selected_requirements`
    (x402/client_base.py:501-513).

    The hook never raises: it runs inside payload creation, and a failed
    bookkeeping read must not cost a payment.
    """
    store: dict[str, Any] = {}

    def capture(ctx: Any) -> None:
        try:
            req = getattr(ctx, "selected_requirements", None)
            if req is None:
                return
            get_amount = getattr(req, "get_amount", None)
            store["amount_atomic"] = (
                get_amount() if callable(get_amount) else getattr(req, "amount", None)
            )
            store["asset"] = getattr(req, "asset", None)
            store["network"] = getattr(req, "network", None)
        except Exception:  # noqa: BLE001 — bookkeeping must never break a payment
            logger.warning("pay_and_fetch: could not capture the signed amount")

    return store, capture


def charged_amount(
    settlement: dict[str, Any] | None,
    signed: dict[str, Any] | None,
) -> tuple[float | None, str | None]:
    """`(amount_usdc, source)` actually charged, or `(None, None)` if unknown.

    The facilitator's own settled amount wins — it is the only figure that
    reflects a partial or overridden settlement. The signed requirement is the
    fallback: what the buyer authorized. Nothing is inferred beyond that; a
    caller that has only a spend *cap* left must label it as such rather than
    pass it off as the charge.
    """
    settlement = settlement or {}
    signed = signed or {}
    network = settlement.get("network") or signed.get("network")
    asset = signed.get("asset")

    amount = atomic_to_units(settlement.get("amount"), network, asset)
    if amount is not None:
        return amount, "settlement"

    amount = atomic_to_units(signed.get("amount_atomic"), network, asset)
    if amount is not None:
        return amount, "authorized"

    return None, None


async def pay_and_fetch(params: PayAndFetchInput) -> dict[str, Any]:
    """Execute x402 paid HTTP request via x402HttpxClient SDK.

    On a settled payment the result also carries `amount_charged_usdc` — what
    was *actually* charged, not `max_price_usdc`, which is only a ceiling. A
    caller that ledgers the cap overstates its own spend for every resource
    that asks for less than the cap, and warden computes its daily/monthly
    caps off that ledger.
    """
    from x402 import NoMatchingRequirementsError
    from x402.http import x402HTTPClient
    from x402.http.clients import x402HttpxClient

    client = _build_x402_client(params.preferred_network, params.max_price_usdc)
    http_client = x402HTTPClient(client)

    signed, capture_signed = signed_requirements_capture()
    client.on_after_payment_creation(capture_signed)

    # Client-level timeout applies to the paid retry too (mainnet settle is slow).
    async with x402HttpxClient(client, timeout=settings.x402_http_timeout) as http:
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

        # A PAYMENT-RESPONSE header proves settlement was *attempted*; only
        # SettleResponse.success proves funds actually moved on-chain.
        settled_ok = settle is not None and getattr(settle, "success", None) is True

        # Only ever report a charge for a payment that actually settled, so no
        # consumer can read an amount off a payment that moved no funds.
        charged, charged_source = (
            charged_amount(settlement_dump, signed) if settled_ok else (None, None)
        )

        return {
            "status_code": response.status_code,
            "body": response.text[:8000],
            "payment_settled": settled_ok,
            "payment_settlement": settlement_dump,
            "settlement_parse_error": settle_error,
            # None when nothing settled, or when neither the facilitator nor
            # the signed requirements yielded a usable amount. Callers must
            # not substitute their price cap without saying so.
            "amount_charged_usdc": charged,
            "amount_charged_source": charged_source,
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


def _normalize_service_tags(raw: list[str] | str | None) -> list[str]:
    """Clamp to facilitator limits: <=5 tags, each <=32 printable chars."""
    if raw is None:
        parts = settings.bazaar_service_tags.split(",")
    elif isinstance(raw, str):
        parts = raw.split(",")
    else:
        parts = list(raw)
    return [t.strip()[:32] for t in parts if t and t.strip()][:5]


def _build_resource_info(params: BuildSellerRequirementsInput, description: str) -> Any:
    """ResourceInfo (url/description/mime + Bazaar service metadata) for a 402.

    ``description`` is the already-clamped value (see _clamp_description) so the
    ResourceInfo cannot exceed the CDP description limit either.

    Per-resource ``service_name`` / ``service_tags`` on the input win over the
    global BAZAAR_* settings so a product is not forced into the wrong category
    (e.g. Minneapolis rental compliance tagged as Base intelligence).
    """
    from x402.schemas import ResourceInfo

    tags = _normalize_service_tags(params.service_tags)
    if params.service_name is not None:
        service_name = params.service_name.strip()[:32] or None
    else:
        service_name = settings.bazaar_service_name.strip()[:32] or None
    return ResourceInfo(
        url=str(params.resource_url),
        description=description,
        mime_type=params.mime_type,
        service_name=service_name,
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

    description = _clamp_description(params.description)

    from x402 import ResourceConfig, x402ResourceServer
    from x402.http import encode_payment_required_header
    from x402.schemas import PaymentRequired

    networks = [n.strip() for n in params.network.split(",") if n.strip()]
    if not networks:
        networks = ["eip155:84532"]

    requirements = []
    
    for net in networks:
        config = ResourceConfig(
            scheme=params.scheme,
            network=net,
            pay_to=pay_to,
            price=params.price,
            description=description,
        )
        facilitator = _facilitator_client(net)
        server = x402ResourceServer(facilitator)
        _register_server_schemes(server)
        try:
            server.initialize()
            requirements.extend(server.build_payment_requirements(config))
        except Exception as exc:
            logger.warning("Facilitator initialize skipped for %s (offline): %s", net, exc)
            from x402.schemas import PaymentRequirements
            price_str = str(params.price or "$0.01").lstrip("$")
            try:
                atomic = float(price_str) * 1_000_000
            except ValueError:
                atomic = 10000.0
            atomic_str = str(int(round(atomic)))
            
            if "solana" in net.lower():
                asset = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            elif "42161" in net:
                asset = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
            else:
                asset = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

            requirements.append(
                PaymentRequirements(
                    scheme=params.scheme,
                    network=net,
                    pay_to=pay_to,
                    amount=atomic_str,
                    asset=asset,
                    max_timeout_seconds=300,
                    extra={},
                )
            )

    # Bazaar discoverability: with a resource_url the challenge carries
    # ResourceInfo, and (unless opted out) the bazaar discovery extension —
    # without it a settled payment through the CDP facilitator catalogs nothing.
    resource_info = None
    extensions = None
    if params.resource_url:
        resource_info = _build_resource_info(params, description)
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
        error=description,
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
        "facilitator_url": _facilitator_url_for(networks[0] if networks else params.network),
        "sdk": "x402ResourceServer.build_payment_requirements",
    }


def resolve_revenue_network() -> str:
    """Network used for pro-tier / tool-credit revenue challenges.

    Explicit REVENUE_NETWORK wins; else the first CDP-routed network when CDP
    creds are set (a deploy with mainnet settlement creds must not hand out
    real quota for free Sepolia USDC); else the default network (local dev).
    """
    if settings.revenue_network:
        return settings.revenue_network
    if settings.cdp_api_key_id and settings.cdp_api_key_secret:
        nets = [n.strip() for n in settings.cdp_networks.split(",") if n.strip()]
        if nets:
            return nets[0]
    return settings.x402_default_network


def build_pro_upgrade_requirements(agent_id: str) -> dict[str, Any]:
    """Build x402 payment requirements to purchase Pro tier (revenue path)."""
    pay_to = settings.x402_pay_to_address
    if not pay_to:
        raise ValueError("X402_PAY_TO_ADDRESS required to collect pro tier payments.")

    result = build_seller_requirements(
        BuildSellerRequirementsInput(
            network=resolve_revenue_network(),
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


def _invalid_payment_result(reason: str) -> dict[str, Any]:
    """402-able failure dict — never raise into a paid HTTP handler."""
    return {
        "is_valid": False,
        "invalid_reason": reason[:300],
        "settlement": None,
        "settlement_error": None,
        "payment_settled": False,
        "facilitator_url": None,
        "sdk": "x402ResourceServer.verify_payment + settle_payment",
    }


async def _verify_and_settle_payment(params: VerifyPaymentInput) -> dict[str, Any]:
    """Seller revenue path: verify then settle via x402ResourceServer + facilitator.

    Decode/verify failures must return ``is_valid=False``, not raise. A paying
    agent retries with PAYMENT-SIGNATURE; an uncaught ValidationError used to
    become HTTP 500 ``internal_error`` (generic handler) instead of a 402
    ``payment_invalid`` the client can retry.
    """
    try:
        payload, requirements = _decode_payment_inputs(
            params.payment_signature, params.payment_required
        )
    except Exception as exc:  # noqa: BLE001 — malformed wire must 402, not 500
        logger.warning("payment decode failed: %s", exc)
        return _invalid_payment_result(f"malformed_payment: {exc}")

    try:
        network = _network_of(requirements)
        server = _resource_server(network)
        verify_result = await server.verify_payment(payload, requirements)
    except Exception as exc:  # noqa: BLE001 — facilitator/SDK faults
        logger.warning("payment verify failed: %s", exc)
        return _invalid_payment_result(f"verify_failed: {exc}")

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


async def build_payment_required_for_resource(
    *,
    resource_url: str,
    description: str | None = None,
    price: str | None = None,
    network: str | None = None,
    pay_to: str | None = None,
    scheme: str = "exact",
    include_bazaar: bool = True,
) -> dict[str, Any]:
    """Build PaymentRequired body + base64 PAYMENT-REQUIRED for a protected URL.

    Used by GET /demo/paid (seller demo). Thin async wrapper over
    build_seller_requirements so tests can monkeypatch this symbol.
    """
    from app.models import BuildSellerRequirementsInput

    pay = pay_to or settings.x402_pay_to_address
    if not pay:
        raise ValueError("X402_PAY_TO_ADDRESS required for seller demo resource")

    net = network or settings.x402_default_network
    prc = price or settings.x402_default_price
    desc = description or "Paid demo resource"

    result = build_seller_requirements(
        BuildSellerRequirementsInput(
            network=net,
            pay_to=pay,
            price=prc,
            scheme=scheme,
            description=desc,
            resource_url=resource_url,
            mime_type="application/json",
            discoverable=include_bazaar,
            discovery_method="GET",
            discovery_input_example={},
            discovery_output_example={
                "ok": True,
                "secret": "x402-seller-demo-ok",
                "payment_settled": True,
            },
            service_name="x402-seller-demo",
            service_tags=["demo", "testnet", "x402"],
        )
    )
    # Decode header back to a JSON-serialisable body for the 402 response payload.
    payment_required_body: dict[str, Any]
    try:
        from x402.http import decode_payment_required_header

        pr = decode_payment_required_header(result["payment_required_header"])
        payment_required_body = (
            pr.model_dump(by_alias=True, exclude_none=True)
            if hasattr(pr, "model_dump")
            else dict(pr)
        )
    except Exception:
        payment_required_body = {
            "error": "Payment required",
            "x402Version": 2,
        }

    return {
        "payment_required": payment_required_body,
        "payment_required_header": result["payment_required_header"],
        "requirements": result.get("requirements") or [],
        "pay_to": pay,
        "price": prc,
        "network": net,
    }


async def verify_and_settle_from_headers(
    payment_signature: str,
    payment_required_header: str,
) -> dict[str, Any]:
    """Verify + settle a buyer PAYMENT-SIGNATURE against PAYMENT-REQUIRED."""
    return await _verify_and_settle_payment(
        VerifyPaymentInput(
            payment_signature=payment_signature,
            payment_required=payment_required_header,
        )
    )


def build_tool_credits_requirements(agent_id: str, credits: int) -> dict[str, Any]:
    """Build x402 payment requirements to purchase per-use MCP tool credits."""
    pay_to = settings.x402_pay_to_address
    if not pay_to:
        raise ValueError("X402_PAY_TO_ADDRESS required to collect tool credit payments.")

    result = build_seller_requirements(
        BuildSellerRequirementsInput(
            network=resolve_revenue_network(),
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