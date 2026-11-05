"""Rate-limit backend selection and distributed adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentforge.platform.infrastructure.valkey_coordination import ValkeyCoordination


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_ms: int = 0
    backend: str = "memory"


class InMemoryRateLimitBackend:
    def __init__(self, capacity: float = 100.0, refill_per_second: float = 10.0) -> None:
        self._capacity = capacity
        self._refill = refill_per_second
        self._buckets: dict[str, tuple[float, float]] = {}

    async def acquire(self, key: str, *, cost: float = 1.0) -> RateLimitDecision:
        import time
        now = time.monotonic()
        tokens, updated = self._buckets.get(key, (self._capacity, now))
        tokens = min(self._capacity, tokens + max(0.0, now - updated) * self._refill)
        allowed = tokens >= cost
        if allowed:
            tokens -= cost
        self._buckets[key] = (tokens, now)
        retry_ms = 0 if allowed else int(((cost - tokens) / self._refill) * 1000)
        return RateLimitDecision(allowed=allowed, retry_after_ms=retry_ms, backend="memory")


class ValkeyRateLimitBackend:
    def __init__(self, coordination: ValkeyCoordination, capacity: float, refill_per_second: float) -> None:
        self._coordination = coordination
        self._capacity = capacity
        self._refill = refill_per_second

    @classmethod
    def from_url(cls, url: str, capacity: float, refill_per_second: float) -> "ValkeyRateLimitBackend":
        return cls(ValkeyCoordination.from_url(url), capacity, refill_per_second)

    async def acquire(self, key: str, *, cost: float = 1.0) -> RateLimitDecision:
        result = await self._coordination.rate_limit(key, capacity=self._capacity, refill_rate=self._refill, cost=cost)
        return RateLimitDecision(allowed=result.allowed, retry_after_ms=result.retry_after_ms, backend="valkey")


def build_rate_limit_backend(settings: Any, coordination: ValkeyCoordination | None = None):
    if settings.rate_limit_backend == "memory":
        return InMemoryRateLimitBackend(settings.rate_limit_capacity, settings.rate_limit_refill_per_second)
    if settings.rate_limit_backend == "valkey":
        if coordination is None:
            coordination = ValkeyCoordination.from_url(settings.valkey_url)
        return ValkeyRateLimitBackend(coordination, settings.rate_limit_capacity, settings.rate_limit_refill_per_second)
    raise ValueError(f"unsupported rate_limit_backend: {settings.rate_limit_backend}")
