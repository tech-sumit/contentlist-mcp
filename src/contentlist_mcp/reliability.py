"""Resilience primitives: per-client rate limiting + per-backend circuit breakers.

These keep the server polite and self-protecting (§8 of docs/design.md):
  • RateLimiter — token bucket per client, so one caller can't starve the rest.
  • CircuitBreaker — trips a flaky backend open so we stop hammering it and fall
    through to the next layer (e.g. SearXNG throttled → Tavily) instead of hard-failing.

Both are pure, synchronous, single-event-loop structures (no locks needed) and are
deliberately dependency-free so the server still runs with zero extras.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class RateLimiter:
    """Token bucket keyed by client id. `rate` tokens/minute, up to `burst` in reserve."""

    def __init__(self, rate_per_min: int, burst: int) -> None:
        self.rate_per_sec = max(rate_per_min, 1) / 60.0
        self.burst = max(burst, 1)
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_ts)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        tokens, last = self._buckets.get(key, (float(self.burst), now))
        tokens = min(self.burst, tokens + (now - last) * self.rate_per_sec)
        if tokens < 1.0:
            self._buckets[key] = (tokens, now)
            return False
        self._buckets[key] = (tokens - 1.0, now)
        return True


@dataclass
class CircuitBreaker:
    """Trip a backend open after repeated failures; probe again after a cooldown."""

    name: str
    fail_threshold: int = 3
    reset_seconds: float = 30.0
    _failures: int = 0
    _opened_at: float | None = field(default=None)

    def allows(self, now: float | None = None) -> bool:
        if self._opened_at is None:
            return True  # closed
        now = time.monotonic() if now is None else now
        # Open: stay closed-off until the cooldown elapses, then allow one probe (half-open).
        return (now - self._opened_at) >= self.reset_seconds

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self, now: float | None = None) -> None:
        self._failures += 1
        if self._failures >= self.fail_threshold:
            self._opened_at = time.monotonic() if now is None else now


async def guarded_call(breaker: CircuitBreaker, factory):
    """Run `factory()` (→ awaitable) behind a breaker. Returns [] on open/failure.

    Backends raise on transport/HTTP errors so the breaker can see them; an empty
    list is a legitimate "no results" and counts as success.
    """
    if not breaker.allows():
        return []
    try:
        result = await factory()
    except Exception:  # noqa: BLE001 - any backend failure trips the breaker, never the agent
        breaker.record_failure()
        return []
    breaker.record_success()
    return result
