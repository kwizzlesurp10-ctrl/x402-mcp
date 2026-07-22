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
    # Signing-key source: "env" (default, deprecated) | keychain/hardware (pluggable).
    key_provider: str = "env"

    x402_pay_to_address: str | None = None
    # Base Network Pulse synthesis inputs (real data sources).
    base_rpc_url: str = "https://mainnet.base.org"
    eth_price_url: str = "https://api.coinbase.com/v2/prices/ETH-USD/spot"
    pulse_depth: int = 12  # blocks sampled per pulse
    # List price for a synthesized Pulse report. $8.00 -> $0.25 on 2026-07-16,
    # then -> $0.05 on 2026-07-22. The $0.25 step assumed a ~$0.30 ecosystem
    # average; measuring the CDP catalog instead (24,788 resources) put the
    # median paid call at $0.014, with ~90% at or under $0.10 — so $0.25 was
    # top-decile pricing, not average. The Pulse costs ~$0 to produce (free RPC
    # + spot price), so volume is worth more here than margin. $0.05 sits in
    # the dense part of the distribution while staying above the sub-cent floor.
    pulse_price: str = "$0.05"
    # Pin the Pulse listing to a fixed product_id so its purchase URL survives a
    # restart. Discovery catalogs (CDP Bazaar) index the URL, which embeds the
    # id — on an ephemeral host a fresh uuid per boot would strand every indexed
    # buyer on a 404. Set to a hex id to enable boot-time republish; empty = off.
    pinned_pulse_product_id: str = ""
    # How old a restored pinned listing may be before startup rebuilds its
    # report. Without this the durable registry would freeze one boot's Pulse
    # forever and keep selling it as live. 0 disables the refresh.
    pinned_pulse_max_age_seconds: int = 900

    # Host OS monitoring (mission control): sampling cadence + health thresholds.
    os_monitor_enabled: bool = True
    os_monitor_interval_seconds: float = 15.0
    os_monitor_history_size: int = 720  # ~3h of samples at 15s cadence
    os_cpu_warn_pct: float = 75.0
    os_cpu_crit_pct: float = 90.0
    os_mem_warn_pct: float = 80.0
    os_mem_crit_pct: float = 92.0
    os_disk_warn_pct: float = 85.0
    os_disk_crit_pct: float = 95.0

    x402_facilitator_url: str = "https://x402.org/facilitator"
    x402_default_network: str = "eip155:84532"
    # Network for revenue challenges (pro tier / tool credits). None resolves
    # via x402_services.resolve_revenue_network(): first CDP network when CDP
    # creds are set, else x402_default_network. Guards against a public deploy
    # selling real quota for free testnet USDC on the Sepolia default.
    revenue_network: str | None = None
    x402_default_price: str = "$0.01"
    # Buyer HTTP timeout; mainnet settlement via a facilitator can take 30-60s,
    # so keep this comfortably above the default httpx timeout.
    x402_http_timeout: float = 90.0

    cdp_discovery_url: str = (
        "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"
    )

    # Bazaar discoverability: when a 402 challenge is built with a resource_url,
    # embed the bazaar discovery extension + service metadata so a settled
    # payment through the CDP facilitator catalogs the endpoint in the Bazaar.
    bazaar_discoverable: bool = True
    # Facilitator-side limits (specs/extensions/bazaar.md): name <= 32 printable
    # ASCII chars; <= 5 tags, each <= 32 chars. Violations are silently dropped.
    bazaar_service_name: str = "x402 MCP Storefront"
    bazaar_service_tags: str = "base,intelligence,x402,data"

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
    # Whether a cycle may spend on upstream inputs. Off by default: measured
    # composite runs carried a real cost basis and then did not sell (LTV:CAC
    # 1.35 against a 3.0 target), while the Pulse product reads free Base RPC
    # and spot data, so its unsold inventory costs nothing and every sale is
    # ~100% margin. A cycle with paid inputs off synthesizes instead of buying.
    swarm_allow_paid_inputs: bool = False
    # Comma-separated fallback upstream x402 URLs used when Bazaar discovery is empty.
    swarm_upstream_urls: str = ""
    swarm_target_ltv_cac: float = 3.0  # target revenue/cost ratio; also the min pricing multiple
    swarm_min_margin_ratio: float = 0.5  # floor on margin/price
    # Network the merchant lists composites on. Must be one the seller facilitator
    # supports (x402.org only settles `exact` on eip155:84532; mainnet selling
    # needs a mainnet-capable facilitator such as Coinbase CDP).
    swarm_sell_network: str = "eip155:84532"

    # Per-transaction Base fee decision (paid HTTP resource, x402-gated).
    # The cheap loop-resident tier beside the $0.05 full Pulse: measured demand
    # concentrates in calls a bot makes on every iteration, and $0.01 gives a
    # first-call entry point at the market's p25 price.
    tx_decision_price: str = "$0.01"

    # MN property compliance product (paid HTTP resource, x402-gated)
    mn_data_base_url: str = (
        "https://services.arcgis.com/afSMGVsC7QlRK1kZ/ArcGIS/rest/services"
    )
    mn_property_check_price: str = "$0.01"


settings = Settings()