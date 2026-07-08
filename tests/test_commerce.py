"""Commerce overlay tests: quota, rate limits, meta envelope, pro tier."""

import json

import pytest

from app.commerce import InMemoryQuotaStore, QuotaExceededError
from app.config import settings


@pytest.fixture
def store() -> InMemoryQuotaStore:
    return InMemoryQuotaStore()


def test_meta_envelope_fields(store: InMemoryQuotaStore) -> None:
    snapshot = store.consume_quota("agent-test-1")
    meta = store.build_meta(snapshot)
    payload = meta.model_dump()

    assert payload["tier"] == "free"
    assert payload["calls_this_month"] == 1
    assert payload["quota_remaining"] == settings.free_tier_monthly_quota - 1
    assert payload["quota_warning"] is False
    assert payload["upgrade_url"] == settings.upgrade_url


def test_quota_warning_at_80_percent(store: InMemoryQuotaStore) -> None:
    agent = "agent-warn"
    threshold = int(settings.free_tier_monthly_quota * 0.8)
    for i in range(threshold):
        store.consume_quota(agent)
        if (i + 1) % settings.free_tier_rate_limit_per_min == 0:
            store._windows[agent].clear()
    snapshot = store.consume_quota(agent)
    assert snapshot.quota_warning is True


def test_rate_limit_429(store: InMemoryQuotaStore) -> None:
    agent = "agent-rl"
    limit = settings.free_tier_rate_limit_per_min
    for _ in range(limit):
        store.consume_quota(agent)

    with pytest.raises(QuotaExceededError) as exc:
        store.consume_quota(agent)

    assert exc.value.detail["error"] == "rate_limit_exceeded"
    assert "retry_after" in exc.value.detail
    assert exc.value.detail["upgrade_url"] == settings.upgrade_url


def test_monthly_quota_429(store: InMemoryQuotaStore) -> None:
    agent = "agent-month"
    for i in range(settings.free_tier_monthly_quota):
        store.consume_quota(agent)
        if (i + 1) % settings.free_tier_rate_limit_per_min == 0:
            store._windows[agent].clear()

    with pytest.raises(QuotaExceededError) as exc:
        store.consume_quota(agent)

    assert exc.value.detail["error"] == "monthly_quota_exceeded"


def test_pro_tier_unlocks_higher_limits(store: InMemoryQuotaStore) -> None:
    agent = "pro-agent"
    store.activate_pro_tier(agent)
    assert store.get_tier(agent) == "pro"
    snapshot = store.consume_quota(agent)
    assert snapshot.tier == "pro"
    assert snapshot.quota_remaining == settings.pro_tier_monthly_quota - 1


def test_tool_response_json_serializable(store: InMemoryQuotaStore) -> None:
    from app.models import ToolResponse

    snapshot = store.consume_quota("agent-json")
    response = ToolResponse(data={"ok": True}, meta=store.build_meta(snapshot))
    serialized = json.dumps(response.model_dump())
    assert "quota_remaining" in serialized


def test_tool_credits_consumed_when_quota_exceeded(store: InMemoryQuotaStore) -> None:
    agent = "credit-agent"
    store.add_credits(agent, 3)

    for i in range(settings.free_tier_monthly_quota):
        store.consume_quota(agent)
        if (i + 1) % settings.free_tier_rate_limit_per_min == 0:
            store._windows[agent].clear()

    snapshot = store.consume_quota(agent)
    assert snapshot.tool_credits_remaining == 2
    assert snapshot.quota_remaining == 0


def test_quota_exceeded_includes_credits_purchase_tools(store: InMemoryQuotaStore) -> None:
    agent = "no-credit-agent"
    for i in range(settings.free_tier_monthly_quota):
        store.consume_quota(agent)
        if (i + 1) % settings.free_tier_rate_limit_per_min == 0:
            store._windows[agent].clear()

    with pytest.raises(QuotaExceededError) as exc:
        store.consume_quota(agent)

    assert exc.value.detail["purchase_credits_tool"] == "purchase_tool_credits"
    assert exc.value.detail["credits_payment_tool"] == "get_tool_credits_requirements"