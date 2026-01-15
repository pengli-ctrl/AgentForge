"""令牌桶限流中间件 — 基于 Token Bucket 算法的请求限流。

令牌桶算法：
- 桶以固定速率（rate）生成令牌
- 每个请求消耗一个令牌
- 桶有最大容量（capacity），满了不再生成
- 没有令牌时请求被拒绝（429 Too Many Requests）

支持按 API Key 或 IP 地址进行独立限流。

部署约束：
- 令牌桶为进程内状态，多 worker 进程间不共享（多进程部署时限流各自独立）。
- 桶字典以任意 client 标识为 key，需要内存淘汰策略（见 ``_evict``），
  否则恶意/普通探测会产生无界的内存增长。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    """令牌桶 — 令牌桶限流算法的核心数据结构。

    Attributes:
        capacity: 桶容量（最大令牌数）。
        rate: 令牌生成速率（令牌/秒）。
        tokens: 当前令牌数。
        last_refill: 上次补充令牌的时间戳。
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

        如果桶中有足够的令牌则消耗并返回 True，否则返回 False。
        消耗前自动补充令牌（按时间差计算）。

        Args:
            tokens: 需要消耗的令牌数。

        Returns:
            是否成功消耗令牌。
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
    """令牌桶限流中间件 — 按客户端限流。

    每个客户端（通过 API Key 或 IP 标识）维护一个独立的令牌桶。
    为避免 ``_buckets`` 无界增长，超过 ``max_buckets`` 或达到淘汰检查
    间隔时会对空闲超过 ``bucket_ttl`` 秒的桶进行清理。

    Args:
        capacity: 桶容量（突发请求上限）。
        rate: 令牌生成速率（请求/秒）。
        max_buckets: 桶字典的最大条目数（内存保护上限）。
        bucket_ttl: 桶的空闲回收时间（秒）。
    """

    def __init__(
        self,
        capacity: float = 100.0,
        rate: float = 10.0,
        max_buckets: int = 10_000,
        bucket_ttl: float = 3_600.0,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            capacity: float，调用方传入的 capacity 参数。
            rate: float，调用方传入的 rate 参数。
            max_buckets: int，调用方传入的 max_buckets 参数。
            bucket_ttl: float，调用方传入的 bucket_ttl 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.capacity = capacity
        self.rate = rate
        self.max_buckets = max_buckets
        self.bucket_ttl = bucket_ttl
        self._buckets: dict[str, TokenBucket] = {}
        self._check_counter = 0

    def _evict_stale(self) -> None:
        """清理空闲超过 ``bucket_ttl`` 的桶。

        桶的 ``last_refill`` 在每次 ``consume`` 时都会更新，
        因此长时间未请求的客户端其桶时间戳必然陈旧，可安全回收。
        """
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
            client_id: 客户端标识（API Key 或 IP）。

        Returns:
            是否允许请求。
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
            client_id: 客户端标识。

        Returns:
            包含 capacity、rate、tokens 的字典，客户端不存在则返回 None。
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
            client_id: 客户端标识。
        """
        if client_id in self._buckets:
            del self._buckets[client_id]
            logger.info("Rate limit bucket reset (client=%s)", client_id)
