"""Valkey协调模块。"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from typing import Any

from redis.exceptions import ResponseError, WatchError

_RATE_LIMIT_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local data = redis.call('HMGET', key, 'tokens', 'timestamp')
local tokens = tonumber(data[1])
local timestamp = tonumber(data[2])
if tokens == nil then tokens = capacity end
if timestamp == nil then timestamp = now end
tokens = math.min(capacity, tokens + math.max(0, now - timestamp) * refill_rate)
local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end
redis.call('HSET', key, 'tokens', tokens, 'timestamp', now)
local ttl = math.max(1, math.ceil(capacity / refill_rate) + 1)
redis.call('EXPIRE', key, ttl)
local retry_after_ms = 0
if allowed == 0 then
  retry_after_ms = math.ceil(((cost - tokens) / refill_rate) * 1000)
end
return {allowed, math.floor(tokens * 1000), retry_after_ms}
"""

_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class RateLimitResult:
    """速率限制结果相关组件。

    Attributes:
        allowed: 允许。
        remaining_millitokens: 字段值。
        retry_after_ms: 重试之后。
    """

    allowed: bool
    remaining_millitokens: int
    retry_after_ms: int


class ValkeyCoordination:
    """Valkey协调相关组件。"""

    def __init__(self, client: Any, *, prefix: str = "agentforge") -> None:
        """初始化 ValkeyCoordination。

        Args:
            client: 客户端实例。
            prefix: 前缀。
        """
        self._client = client
        self._prefix = prefix.strip(":") or "agentforge"

    @classmethod
    def from_url(cls, url: str, *, prefix: str = "agentforge") -> "ValkeyCoordination":
        """从URL构造当前对象。

        Args:
            url: 目标 URL。
            prefix: 前缀。

        Returns:
            处理结果对象。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        try:
            import redis.asyncio as aioredis
        except ImportError as exc:
            raise RuntimeError("redis package is required for ValkeyCoordination") from exc
        return cls(aioredis.from_url(url, decode_responses=True), prefix=prefix)

    async def ping(self) -> bool:
        """探活Valkey协调。

        Returns:
            操作是否成功。
        """
        return bool(await self._client.ping())

    async def close(self) -> None:
        """关闭Valkeycoordination。"""
        close = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if close is not None:
            await close()

    async def rate_limit(
        self,
        key: str,
        *,
        capacity: float,
        refill_rate: float,
        cost: float = 1.0,
        now: float | None = None,
    ) -> RateLimitResult:
        """处理速率限制。

        Args:
            key: 缓存或配置键。
            capacity: 输入参数。
            refill_rate: 速率。
            cost: 成本。
            now: 输入参数。

        Returns:
            速率限制结果结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
            Exception: 操作无法完成时抛出。
        """
        if capacity <= 0 or refill_rate <= 0 or cost <= 0:
            raise ValueError("capacity, refill_rate and cost must be positive")
        timestamp = time.time() if now is None else now
        cache_key = self._key("rate", key)
        try:
            raw = await self._client.eval(
                _RATE_LIMIT_LUA,
                1,
                cache_key,
                str(capacity),
                str(refill_rate),
                str(timestamp),
                str(cost),
            )
        except ResponseError as exc:
            if "unknown command" not in str(exc).lower():
                raise
            return await self._rate_limit_transactional(
                cache_key,
                capacity=capacity,
                refill_rate=refill_rate,
                cost=cost,
                now=timestamp,
            )
        return RateLimitResult(
            allowed=bool(int(raw[0])),
            remaining_millitokens=int(raw[1]),
            retry_after_ms=max(0, int(raw[2])),
        )

    async def _rate_limit_transactional(
        self,
        key: str,
        *,
        capacity: float,
        refill_rate: float,
        cost: float,
        now: float,
    ) -> RateLimitResult:
        """处理速率限制。

        Args:
            key: 缓存或配置键。
            capacity: 输入参数。
            refill_rate: 速率。
            cost: 成本。
            now: 输入参数。

        Returns:
            速率限制结果结果。
        """
        while True:
            async with self._client.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    tokens_raw, timestamp_raw = await pipe.hmget(key, "tokens", "timestamp")
                    tokens = float(tokens_raw) if tokens_raw is not None else capacity
                    previous = float(timestamp_raw) if timestamp_raw is not None else now
                    tokens = min(capacity, tokens + max(0.0, now - previous) * refill_rate)
                    allowed = tokens >= cost
                    if allowed:
                        tokens -= cost
                    pipe.multi()
                    pipe.hset(key, mapping={"tokens": tokens, "timestamp": now})
                    pipe.expire(key, max(1, math.ceil(capacity / refill_rate) + 1))
                    await pipe.execute()
                    retry_after_ms = (
                        0 if allowed else math.ceil(((cost - tokens) / refill_rate) * 1000)
                    )
                    return RateLimitResult(
                        allowed=allowed,
                        remaining_millitokens=math.floor(tokens * 1000),
                        retry_after_ms=max(0, retry_after_ms),
                    )
                except WatchError:
                    continue

    async def set_json(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        """设置JSON。

        Args:
            key: 缓存或配置键。
            value: 待处理值。
            ttl_seconds: 输入参数。
        """
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        cache_key = self._key("cache", key)
        if ttl_seconds is not None and ttl_seconds > 0:
            await self._client.set(cache_key, encoded, ex=ttl_seconds)
        else:
            await self._client.set(cache_key, encoded)

    async def get_json(self, key: str) -> Any | None:
        """读取JSON。

        Args:
            key: 缓存或配置键。

        Returns:
            无结果。
        """
        value = await self._client.get(self._key("cache", key))
        return json.loads(value) if value is not None else None

    async def delete(self, key: str) -> bool:
        """删除Valkeycoordination。

        Args:
            key: 缓存或配置键。

        Returns:
            操作是否成功。
        """
        return bool(await self._client.delete(self._key("cache", key)))

    async def invalidate_prefix(self, prefix: str) -> int:
        """失效前缀。

        Args:
            prefix: 前缀。

        Returns:
            整数结果。
        """
        deleted = 0
        async for key in self._client.scan_iter(match=self._key("cache", f"{prefix}*")):
            deleted += int(await self._client.delete(key))
        return deleted

    async def acquire_lock(self, name: str, token: str, *, ttl_seconds: int = 30) -> bool:
        """判断锁是否成立。

        Args:
            name: 资源或对象名称。
            token: 待验证的访问令牌。
            ttl_seconds: 输入参数。

        Returns:
            操作是否成功。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        result = await self._client.set(
            self._key("lock", name),
            token,
            nx=True,
            px=ttl_seconds * 1000,
        )
        return bool(result)

    async def release_lock(self, name: str, token: str) -> bool:
        """释放锁。

        Args:
            name: 资源或对象名称。
            token: 待验证的访问令牌。

        Returns:
            操作是否成功。

        Raises:
            Exception: 操作无法完成时抛出。
        """
        lock_key = self._key("lock", name)
        try:
            result = await self._client.eval(_RELEASE_LOCK_LUA, 1, lock_key, token)
            return bool(int(result))
        except ResponseError as exc:
            if "unknown command" not in str(exc).lower():
                raise
            if await self._client.get(lock_key) != token:
                return False
            return bool(await self._client.delete(lock_key))

    def _key(self, namespace: str, key: str) -> str:
        """执行键。

        Args:
            namespace: 输入参数。
            key: 缓存或配置键。

        Returns:
            字符串结果。
        """
        return f"{self._prefix}:{namespace}:{key}"


__all__ = ["RateLimitResult", "ValkeyCoordination"]
