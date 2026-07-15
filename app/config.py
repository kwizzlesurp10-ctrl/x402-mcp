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

    # Optional bearer token to protect /quota endpoint. If unset, endpoint is open.
    operator_token: str | None = None

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

    # MN property compliance product (paid HTTP resource, x402-gated)
    mn_data_base_url: str = (
        "https://services.arcgis.com/afSMGVsC7QlRK1kZ/ArcGIS/rest/services"
    )
    mn_property_check_price: str = "$0.01"


settings = Settings()