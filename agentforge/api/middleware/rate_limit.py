"""令牌桶限流中间件 — 基于 Token Bucket 算法的请求限流。

令牌桶算法：
- 桶以固定速率（rate）生成令牌
- 每个请求消耗一个令牌
- 桶有最大容量（capacity），满了不再生成
- 没有令牌时请求被拒绝（429 Too Many Requests）

支持按 API Key 或 IP 地址进行独立限流。
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

    Args:
        capacity: 桶容量（突发请求上限）。
        rate: 令牌生成速率（请求/秒）。
    """

    def __init__(
        self,
        capacity: float = 100.0,
        rate: float = 10.0,
    ) -> None:
        self.capacity = capacity
        self.rate = rate
        self._buckets: dict[str, TokenBucket] = {}

    def check(self, client_id: str) -> bool:
        """检查客户端是否被允许请求。

        Args:
            client_id: 客户端标识（API Key 或 IP）。

        Returns:
            是否允许请求。
        """
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
