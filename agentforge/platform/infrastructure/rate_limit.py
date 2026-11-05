"""提供请求限流与后端切换。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentforge.platform.infrastructure.valkey_coordination import ValkeyCoordination


@dataclass(frozen=True)
class RateLimitDecision:
    """提供请求限流与后端切换。

    Attributes:
        allowed: 配置字段。
        retry_after_ms: 配置字段。
        backend: 配置字段。
    """

    allowed: bool
    retry_after_ms: int = 0
    backend: str = "memory"


class InMemoryRateLimitBackend:
    """提供请求限流与后端切换。"""

    def __init__(self, capacity: float = 100.0, refill_per_second: float = 10.0) -> None:
        """提供请求限流与后端切换。

        Args:
            capacity: 调用该函数所需的输入值。
            refill_per_second: 调用该函数所需的输入值。
        """
        self._capacity = capacity
        self._refill = refill_per_second
        self._buckets: dict[str, tuple[float, float]] = {}

    async def acquire(self, key: str, *, cost: float = 1.0) -> RateLimitDecision:
        """提供请求限流与后端切换。

            Args:
                key: 调用该函数所需的输入值。
                cost: 调用该函数所需的输入值。

            Returns:
        当前操作的结构化结果。
        """
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
    """提供请求限流与后端切换。"""

    def __init__(
        self, coordination: ValkeyCoordination, capacity: float, refill_per_second: float
    ) -> None:
        """提供请求限流与后端切换。

        Args:
            coordination: 调用该函数所需的输入值。
            capacity: 调用该函数所需的输入值。
            refill_per_second: 调用该函数所需的输入值。
        """
        self._coordination = coordination
        self._capacity = capacity
        self._refill = refill_per_second

    @classmethod
    def from_url(
        cls, url: str, capacity: float, refill_per_second: float
    ) -> "ValkeyRateLimitBackend":
        """提供请求限流与后端切换。

            Args:
                url: 调用该函数所需的输入值。
                capacity: 调用该函数所需的输入值。
                refill_per_second: 调用该函数所需的输入值。

            Returns:
        当前操作的结构化结果。
        """
        return cls(ValkeyCoordination.from_url(url), capacity, refill_per_second)

    async def acquire(self, key: str, *, cost: float = 1.0) -> RateLimitDecision:
        """提供请求限流与后端切换。

            Args:
                key: 调用该函数所需的输入值。
                cost: 调用该函数所需的输入值。

            Returns:
        当前操作的结构化结果。
        """
        result = await self._coordination.rate_limit(
            key, capacity=self._capacity, refill_rate=self._refill, cost=cost
        )
        return RateLimitDecision(
            allowed=result.allowed, retry_after_ms=result.retry_after_ms, backend="valkey"
        )


def build_rate_limit_backend(settings: Any, coordination: ValkeyCoordination | None = None):
    """提供请求限流与后端切换。

    Args:
        settings: 调用该函数所需的输入值。
        coordination: 调用该函数所需的输入值。

    Raises:
    ValueError: 输入不合法时抛出。
    """
    if settings.rate_limit_backend == "memory":
        return InMemoryRateLimitBackend(
            settings.rate_limit_capacity, settings.rate_limit_refill_per_second
        )
    if settings.rate_limit_backend == "valkey":
        if coordination is None:
            coordination = ValkeyCoordination.from_url(settings.valkey_url)
        return ValkeyRateLimitBackend(
            coordination, settings.rate_limit_capacity, settings.rate_limit_refill_per_second
        )
    raise ValueError(f"unsupported rate_limit_backend: {settings.rate_limit_backend}")
