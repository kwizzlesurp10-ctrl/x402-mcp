"""Per-IP rate limiter for GET /probe (10 requests per minute)."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class ProbeRateLimitExceeded(Exception):
    """Raised when a client exceeds the probe rate limit."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Probe rate limit exceeded; retry after {retry_after}s")


class ProbeRateLimiter:
    """In-memory sliding window: max 10 probes per minute per client IP."""

    def __init__(self, *, limit: int = 10, window_seconds: float = 60.0) -> None:
        self._limit = limit
        self._window = window_seconds
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client_ip: str) -> None:
        now = time.time()
        window = self._windows[client_ip]
        cutoff = now - self._window
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= self._limit:
            retry_after = max(int(self._window - (now - window[0])), 1)
            raise ProbeRateLimitExceeded(retry_after)

        window.append(now)


probe_rate_limiter = ProbeRateLimiter()