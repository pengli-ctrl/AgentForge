"""速率限制模块。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    """令牌桶 — 令牌桶限流算法的核心数据结构。

    Attributes:
        capacity: 字段值。
        rate: 速率。
        tokens: 令牌用量。
        last_refill: 字段值。
    """

    capacity: float
    rate: float
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """初始化时桶满。"""
        if self.tokens == 0.0:
            self.tokens = self.capacity

    def consume(self, tokens: float = 1.0) -> bool:
        """消耗令牌。

        Args:
            tokens: 输入参数。

        Returns:
            操作是否成功。
        """
        now = time.time()
        elapsed = now - self.last_refill

        # 按速率补充令牌
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False


class RateLimitMiddleware:
    """令牌桶限流中间件 — 按客户端限流。"""

    def __init__(
        self,
        capacity: float = 100.0,
        rate: float = 10.0,
        max_buckets: int = 10_000,
        bucket_ttl: float = 3_600.0,
    ) -> None:
        """初始化 RateLimitMiddleware。

        Args:
            capacity: 输入参数。
            rate: 速率。
            max_buckets: 最大。
            bucket_ttl: 存储桶。
        """
        self.capacity = capacity
        self.rate = rate
        self.max_buckets = max_buckets
        self.bucket_ttl = bucket_ttl
        self._buckets: dict[str, TokenBucket] = {}
        self._check_counter = 0

    def _evict_stale(self) -> None:
        """淘汰过期。"""
        now = time.time()
        stale = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.last_refill > self.bucket_ttl
        ]
        for key in stale:
            del self._buckets[key]
        if stale:
            logger.info(
                "Rate limit bucket eviction: removed %d idle bucket(s) (remaining=%d)",
                len(stale),
                len(self._buckets),
            )

    def _evict_lru(self) -> None:
        """当桶数量仍超过上限时，按最近最少使用移除最旧的桶。"""
        while len(self._buckets) >= self.max_buckets and self._buckets:
            oldest_key = min(
                self._buckets,
                key=lambda key: self._buckets[key].last_refill,
            )
            del self._buckets[oldest_key]
            logger.warning(
                "Rate limit bucket overflow: evicted LRU bucket (client=%s, size=%d)",
                oldest_key,
                len(self._buckets),
            )

    def check(self, client_id: str) -> bool:
        """检查客户端是否被允许请求。

        Args:
            client_id: 客户端 ID。

        Returns:
            操作是否成功。
        """
        # 周期性执行淘汰，避免每次请求都做全量扫描。
        self._check_counter += 1
        if self._check_counter % 100 == 0 or len(self._buckets) >= self.max_buckets:
            self._evict_stale()
            # 若清理后仍触顶（如大量活跃客户端），再按 LRU 兜底淘汰。
            if len(self._buckets) >= self.max_buckets:
                self._evict_lru()

        if client_id not in self._buckets:
            self._buckets[client_id] = TokenBucket(
                capacity=self.capacity,
                rate=self.rate,
            )

        allowed = self._buckets[client_id].consume()

        if not allowed:
            logger.warning(
                "Rate limit exceeded (client=%s, capacity=%.0f, rate=%.1f/s)",
                client_id,
                self.capacity,
                self.rate,
            )

        return allowed

    def get_bucket_status(self, client_id: str) -> dict[str, float] | None:
        """获取客户端的令牌桶状态。

        Args:
            client_id: 客户端 ID。

        Returns:
            结构化结果字典。
        """
        bucket = self._buckets.get(client_id)
        if bucket is None:
            return None
        return {
            "capacity": bucket.capacity,
            "rate": bucket.rate,
            "tokens": round(bucket.tokens, 2),
        }

    def reset(self, client_id: str) -> None:
        """重置客户端的令牌桶。

        Args:
            client_id: 客户端 ID。
        """
        if client_id in self._buckets:
            del self._buckets[client_id]
            logger.info("Rate limit bucket reset (client=%s)", client_id)
