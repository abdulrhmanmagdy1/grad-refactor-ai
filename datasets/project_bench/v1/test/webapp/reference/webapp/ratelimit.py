"""Sliding-window rate limiting per client key."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    """Allows at most ``limit`` requests per key in any ``window`` seconds."""

    def __init__(
        self,
        limit: int,
        window: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window <= 0:
            raise ValueError("window must be positive")
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def _recent(self, key: str, now: float) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        return hits

    def allow(self, key: str) -> bool:
        """Record a request for ``key`` and say whether it is within the limit.

        Rejected requests are not recorded, so a client that keeps retrying
        gets through again once its earlier requests leave the window.
        """
        now = self._clock()
        hits = self._recent(key, now)
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def retry_after(self, key: str) -> float:
        """Seconds until ``key`` may make another request (0 when it may now)."""
        now = self._clock()
        hits = self._recent(key, now)
        if len(hits) < self.limit:
            return 0.0
        return hits[0] + self.window - now

    def reset(self, key: str) -> None:
        """Forget every request recorded for ``key``."""
        self._hits.pop(key, None)
