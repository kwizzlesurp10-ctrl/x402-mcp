"""Pydantic models for x402 MCP tools and commerce envelopes."""

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class ResponseMeta(BaseModel):
    """Mandatory commerce meta envelope on every successful MCP tool response."""

    tier: str = Field(description="Current billing tier: free | pro")
    calls_this_month: int = Field(description="MCP tool calls consumed this month")
    quota_remaining: int = Field(description="Remaining MCP calls this month")
    quota_warning: bool = Field(
        description="True when quota consumption is at or above 80%"
    )
    rate_limit_remaining: int = Field(
        description="Remaining MCP calls in the current 1-minute window"
    )
    tool_credits_remaining: int = Field(
        default=0,
        description="Per-use tool credits purchased via x402 (consumed when monthly quota exceeded)",
    )
    upgrade_url: str = Field(description="URL for tier upgrade")
    agent_id: str = Field(description="Per-agent tracking identifier")


class ToolResponse(BaseModel):
    """Standard MCP tool response wrapper."""

    data: dict[str, Any]
    meta: ResponseMeta


class DiscoverServicesInput(BaseModel):
    """Discover x402 Bazaar services."""

    query: str | None = Field(
        default=None,
        description="Optional keyword filter applied client-side to discovered services",
    )
    limit: int = Field(default=20, ge=1, le=100, description="Max services to return")
    max_price_usdc: float | None = Field(
        default=None,
        ge=0,
        description="Filter services accepting payments at or below this USDC amount",
    )


class GetPaymentRequirementsInput(BaseModel):
    """Probe a URL for x402 payment requirements."""

    url: HttpUrl = Field(description="HTTP(S) URL to probe")
    method: str = Field(default="GET", description="HTTP method")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Optional request headers",
    )


class PayAndFetchInput(BaseModel):
    """Pay via x402 and fetch a protected resource."""

    url: HttpUrl = Field(description="Paid resource URL")
    method: str = Field(default="GET", description="HTTP method")
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = Field(default=None, description="Optional request body")
    preferred_network: str | None = Field(
        default=None,
        description="CAIP-2 network preference, e.g. eip155:8453 for Base mainnet",
    )
    max_price_usdc: float | None = Field(
        default=None,
        gt=0,
        description="Spend cap: refuse to sign if every accepted payment option "
        "exceeds this USDC amount",
    )


class BuildSellerRequirementsInput(BaseModel):
    """Build seller-side x402 payment requirements for an endpoint."""

    network: str = Field(
        default="eip155:84532",
        description="CAIP-2 network identifier",
    )
    pay_to: str | None = Field(
        default=None,
        description="Recipient wallet address (defaults to X402_PAY_TO_ADDRESS)",
    )
    price: str = Field(default="$0.01", description="Price string, e.g. $0.01")
    scheme: str = Field(default="exact", description="Payment scheme: exact | upto")
    description: str = Field(
        default="Paid MCP-backed API access",
        description="Human-readable resource description",
    )
    # Bazaar discoverability (all optional, backward compatible): when
    # resource_url is set the 402 challenge carries ResourceInfo, and — unless
    # opted out — the bazaar discovery extension the CDP facilitator needs to
    # catalog the endpoint when a payment settles.
    resource_url: str | None = Field(
        default=None,
        description=(
            "Public URL of the payable resource. Required for Bazaar discovery; "
            "without it the 402 challenge carries no resource info or extension."
        ),
    )
    mime_type: str | None = Field(
        default="application/json",
        description="MIME type of the paid resource (resource info metadata)",
    )
    discoverable: bool | None = Field(
        default=None,
        description=(
            "Embed the bazaar discovery extension in the 402 challenge "
            "(None = BAZAAR_DISCOVERABLE setting)"
        ),
    )
    discovery_method: Literal["GET", "HEAD", "DELETE", "POST", "PUT", "PATCH"] = Field(
        default="GET",
        description="HTTP method buyers use to call the resource",
    )
    discovery_input_example: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Example input: query params for GET/HEAD/DELETE, "
            "JSON body for POST/PUT/PATCH"
        ),
    )
    discovery_output_example: dict[str, Any] | None = Field(
        default=None,
        description="Small example of the JSON response a paying buyer receives",
    )


class VerifyPaymentInput(BaseModel):
    """Verify an x402 payment payload against requirements."""

    payment_signature: str = Field(
        description="Base64 PAYMENT-SIGNATURE header value from the buyer"
    )
    payment_required: str = Field(
        description="Base64 PAYMENT-REQUIRED header value from the 402 response"
    )


class SupportedNetworksOutput(BaseModel):
    """Known x402 network and facilitator reference data."""

    networks: list[dict[str, str]]
    facilitators: list[dict[str, str]]
    default_network: str
    protocol_version: str = "v2"
    headers: dict[str, str]
    facilitator_supported: dict[str, Any] | None = None