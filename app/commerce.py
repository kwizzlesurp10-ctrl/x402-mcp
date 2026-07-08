"""MCP commerce overlay: agent tracking, tiers, quota, rate limits, x402 pro unlock.

Redis migration path:
    Replace InMemoryQuotaStore with RedisQuotaStore using settings.redis_url.
    Keys: agent:{id}:month:{YYYY-MM}, agent:{id}:rl:{minute_bucket}, agent:{id}:tier
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException

from app.config import settings
from app.models import ResponseMeta


@dataclass
class QuotaSnapshot:
    agent_id: str
    calls_this_month: int
    quota_remaining: int
    quota_warning: bool
    rate_limit_remaining: int
    tier: str
    tool_credits_remaining: int = 0


class QuotaExceededError(Exception):
    """Raised when MCP quota or rate limit is exceeded (maps to 429 in MCP tools)."""

    def __init__(self, detail: dict) -> None:
        self.detail = detail
        super().__init__(detail.get("message", "quota exceeded"))


class InMemoryQuotaStore:
    """In-memory quota + rate limit store. Swap for Redis in production."""

    def __init__(self) -> None:
        self._agent_ids: dict[str, str] = {}
        self._tiers: dict[str, str] = {}
        self._monthly: dict[str, int] = defaultdict(int)
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._pro_activations: dict[str, str] = {}  # agent_id -> activated_at iso
        self._credits: dict[str, int] = defaultdict(int)

    def resolve_agent_id(self, provided: str | None) -> str:
        if provided:
            return provided
        token = str(uuid.uuid4())
        self._agent_ids[token] = token
        return token

    def get_tier(self, agent_id: str) -> str:
        return self._tiers.get(agent_id, "free")

    def activate_pro_tier(self, agent_id: str) -> None:
        """Unlock pro tier after verified x402 payment (revenue collection path)."""
        self._tiers[agent_id] = "pro"
        self._pro_activations[agent_id] = datetime.now(UTC).isoformat()

    def get_credits(self, agent_id: str) -> int:
        return self._credits[agent_id]

    def add_credits(self, agent_id: str, amount: int) -> int:
        """Credit balance after verified x402 per-use purchase."""
        self._credits[agent_id] += amount
        return self._credits[agent_id]

    def tier_limits(self, tier: str) -> tuple[int, int]:
        if tier == "pro":
            return (
                settings.pro_tier_monthly_quota,
                settings.pro_tier_rate_limit_per_min,
            )
        return (
            settings.free_tier_monthly_quota,
            settings.free_tier_rate_limit_per_min,
        )

    def _month_key(self, agent_id: str) -> str:
        month = datetime.now(UTC).strftime("%Y-%m")
        return f"{agent_id}:{month}"

    def _prune_window(self, agent_id: str, now: float) -> None:
        window = self._windows[agent_id]
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.popleft()

    def consume_quota(self, agent_id: str) -> QuotaSnapshot:
        """Preemptive quota check — call BEFORE executing tool work."""
        now = time.time()
        self._prune_window(agent_id, now)

        tier = self.get_tier(agent_id)
        quota, rate_limit = self.tier_limits(tier)

        month_key = self._month_key(agent_id)
        calls = self._monthly[month_key]
        window = self._windows[agent_id]

        if calls >= quota:
            credits = self._credits[agent_id]
            if credits > 0:
                self._credits[agent_id] = credits - 1
                new_calls = calls + 1
                self._monthly[month_key] = new_calls
                window.append(now)
                new_rate_remaining = max(rate_limit - len(window), 0)
                return QuotaSnapshot(
                    agent_id=agent_id,
                    calls_this_month=new_calls,
                    quota_remaining=0,
                    quota_warning=True,
                    rate_limit_remaining=new_rate_remaining,
                    tier=tier,
                    tool_credits_remaining=self._credits[agent_id],
                )

            raise QuotaExceededError(
                {
                    "error": "monthly_quota_exceeded",
                    "message": f"{tier} tier monthly MCP quota exceeded.",
                    "tier": tier,
                    "calls_this_month": calls,
                    "quota_remaining": 0,
                    "tool_credits_remaining": 0,
                    "upgrade_url": settings.upgrade_url,
                    "upgrade_payment_tool": "get_pro_upgrade_requirements",
                    "activate_tool": "activate_pro_tier",
                    "credits_payment_tool": "get_tool_credits_requirements",
                    "purchase_credits_tool": "purchase_tool_credits",
                    "retry_after": self._seconds_until_next_month(),
                }
            )

        if len(window) >= rate_limit:
            retry_after = max(int(60 - (now - window[0])), 1)
            raise QuotaExceededError(
                {
                    "error": "rate_limit_exceeded",
                    "message": f"MCP rate limit exceeded ({rate_limit}/min on {tier} tier).",
                    "tier": tier,
                    "rate_limit_remaining": 0,
                    "upgrade_url": settings.upgrade_url,
                    "upgrade_payment_tool": "get_pro_upgrade_requirements",
                    "activate_tool": "activate_pro_tier",
                    "retry_after": retry_after,
                }
            )

        self._monthly[month_key] = calls + 1
        window.append(now)

        new_calls = self._monthly[month_key]
        new_remaining = max(quota - new_calls, 0)
        warning = new_calls / quota >= 0.8 if quota else False
        new_rate_remaining = max(rate_limit - len(window), 0)

        return QuotaSnapshot(
            agent_id=agent_id,
            calls_this_month=new_calls,
            quota_remaining=new_remaining,
            quota_warning=warning,
            rate_limit_remaining=new_rate_remaining,
            tier=tier,
            tool_credits_remaining=self._credits[agent_id],
        )

    def _seconds_until_next_month(self) -> int:
        now = datetime.now(UTC)
        if now.month == 12:
            next_month = datetime(now.year + 1, 1, 1, tzinfo=UTC)
        else:
            next_month = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
        return max(int((next_month - now).total_seconds()), 1)

    def peek(self, agent_id: str) -> QuotaSnapshot:
        now = time.time()
        self._prune_window(agent_id, now)
        tier = self.get_tier(agent_id)
        quota, rate_limit = self.tier_limits(tier)
        month_key = self._month_key(agent_id)
        calls = self._monthly[month_key]
        window = self._windows[agent_id]
        remaining = max(quota - calls, 0)
        rate_remaining = max(rate_limit - len(window), 0)
        warning = calls / quota >= 0.8 if quota else False
        return QuotaSnapshot(
            agent_id=agent_id,
            calls_this_month=calls,
            quota_remaining=remaining,
            quota_warning=warning,
            rate_limit_remaining=rate_remaining,
            tier=tier,
            tool_credits_remaining=self._credits[agent_id],
        )

    def build_meta(self, snapshot: QuotaSnapshot) -> ResponseMeta:
        return ResponseMeta(
            tier=snapshot.tier,
            calls_this_month=snapshot.calls_this_month,
            quota_remaining=snapshot.quota_remaining,
            quota_warning=snapshot.quota_warning,
            rate_limit_remaining=snapshot.rate_limit_remaining,
            tool_credits_remaining=snapshot.tool_credits_remaining,
            upgrade_url=settings.upgrade_url,
            agent_id=snapshot.agent_id,
        )


quota_store = InMemoryQuotaStore()