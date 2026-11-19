"""In-memory rate limiting per client IP plus a global daily quota."""

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

WINDOW_SECONDS = 60.0
SECONDS_PER_DAY = 86400
MAX_TRACKED_KEYS = 10_000
UNKNOWN_CLIENT = "unknown"


@dataclass(frozen=True)
class RateDecision:
    is_allowed: bool
    retry_after_seconds: int = 0


ALLOWED = RateDecision(is_allowed=True)


def _denied(wait_seconds: float) -> RateDecision:
    return RateDecision(is_allowed=False, retry_after_seconds=max(1, math.ceil(wait_seconds)))


class StrictRateLimiter:
    """Sliding 60 s window per key and a daily quota (UTC) shared by every key."""

    def __init__(
        self,
        per_minute: int,
        daily_quota: int,
        clock: Callable[[], float] = time.time,
        max_keys: int = MAX_TRACKED_KEYS,
    ) -> None:
        self._per_minute = per_minute
        self._daily_quota = daily_quota
        self._clock = clock
        self._max_keys = max_keys
        self._windows: dict[str, deque[float]] = {}
        self._day = -1
        self._used_today = 0
        self._lock = threading.Lock()

    def check(self, key: str) -> RateDecision:
        """Record the request and allow it, or say how long to wait."""
        with self._lock:
            now = self._clock()
            self._roll_day(now)
            if self._used_today >= self._daily_quota:
                return _denied((self._day + 1) * SECONDS_PER_DAY - now)
            window = self._windows.setdefault(key, deque())
            self._drop_expired(window, now)
            if len(window) >= self._per_minute:
                return _denied(window[0] + WINDOW_SECONDS - now)
            window.append(now)
            self._used_today += 1
            if len(self._windows) > self._max_keys:
                self._prune(now)
            return ALLOWED

    def _roll_day(self, now: float) -> None:
        day = int(now // SECONDS_PER_DAY)
        if day != self._day:
            self._day = day
            self._used_today = 0

    @staticmethod
    def _drop_expired(window: deque[float], now: float) -> None:
        while window and window[0] <= now - WINDOW_SECONDS:
            window.popleft()

    def _prune(self, now: float) -> None:
        for key, window in list(self._windows.items()):
            self._drop_expired(window, now)
            if not window:
                del self._windows[key]


def client_ip(forwarded_for: str | None, peer: str | None) -> str:
    """The last non-empty X-Forwarded-For value (added by the Google front end), else the peer."""
    if forwarded_for:
        values = [value.strip() for value in forwarded_for.split(",") if value.strip()]
        if values:
            return values[-1]
    return peer or UNKNOWN_CLIENT
