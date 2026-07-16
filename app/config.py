"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8402
    upgrade_url: str = "http://localhost:8402/upgrade"
    public_base_url: str = "http://localhost:8402"

    free_tier_monthly_quota: int = 500
    free_tier_rate_limit_per_min: int = 10
    pro_tier_monthly_quota: int = 50_000
    pro_tier_rate_limit_per_min: int = 120
    pro_tier_price: str = "$29.00"

    tool_credit_pack_size: int = 100
    tool_credit_pack_price: str = "$1.00"

    # Redis-ready: set REDIS_URL to migrate from in-memory stores.
    redis_url: str | None = None

    evm_private_key: str | None = None
    svm_private_key: str | None = None

    x402_pay_to_address: str | None = None
    # Base Network Pulse synthesis inputs (real data sources).
    base_rpc_url: str = "https://mainnet.base.org"
    eth_price_url: str = "https://api.coinbase.com/v2/prices/ETH-USD/spot"
    pulse_depth: int = 12  # blocks sampled per pulse
    pulse_price: str = "$8.00"  # list price for a synthesized Pulse report

    x402_facilitator_url: str = "https://x402.org/facilitator"
    x402_default_network: str = "eip155:84532"
    x402_default_price: str = "$0.01"
    # Buyer HTTP timeout; mainnet settlement via a facilitator can take 30-60s,
    # so keep this comfortably above the default httpx timeout.
    x402_http_timeout: float = 90.0

    cdp_discovery_url: str = (
        "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"
    )

    # Coinbase CDP facilitator (required to verify/settle x402 on Base mainnet;
    # x402.org only settles `exact` on Base Sepolia). Ed25519 API key from the
    # CDP portal — rotate any key that has ever been shared in plaintext.
    cdp_api_key_id: str | None = None
    cdp_api_key_secret: str | None = None
    cdp_facilitator_url: str = "https://api.cdp.coinbase.com/platform/v2/x402"
    # Networks routed to the CDP facilitator when CDP creds are set (comma-sep).
    cdp_networks: str = "eip155:8453"

    # Stripe fiat payment rail (primary for card/bank checkout)
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_publishable_key: str | None = None

    # Mission-control dashboard: gate POST /seller/requirements (default read-only)
    dashboard_actions: bool = False

    # Swarm Agency: buy cheap upstream x402 services, compose, resell the composite.
    swarm_enabled: bool = False
    swarm_markup: float = 3.0  # composite price = cost basis * markup
    swarm_min_price_usdc: float = 0.01  # price floor for a composite product
    swarm_max_upstream_calls: int = 3  # max upstream buys per run
    # Comma-separated fallback upstream x402 URLs used when Bazaar discovery is empty.
    swarm_upstream_urls: str = ""
    swarm_target_ltv_cac: float = 3.0  # target revenue/cost ratio; also the min pricing multiple
    swarm_min_margin_ratio: float = 0.5  # floor on margin/price
    # Network the merchant lists composites on. Must be one the seller facilitator
    # supports (x402.org only settles `exact` on eip155:84532; mainnet selling
    # needs a mainnet-capable facilitator such as Coinbase CDP).
    swarm_sell_network: str = "eip155:84532"


settings = Settings()