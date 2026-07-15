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
    x402_facilitator_url: str = "https://x402.org/facilitator"
    x402_default_network: str = "eip155:84532"
    x402_default_price: str = "$0.01"

    cdp_discovery_url: str = (
        "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"
    )

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


settings = Settings()