"""Redis状态模块。"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class RedisStateStore:
    """Redis状态相关组件。"""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "agentforge:snapshot",
        default_ttl: int = 86400,
    ) -> None:
        """初始化 RedisStateStore。

        Args:
            redis_url: RedisURL。
            key_prefix: 键前缀。
            default_ttl: 默认。
        """
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self._redis: Any = None
        self._fallback: dict[str, str] = {}

    async def connect(self) -> None:
        """连接Redis状态。"""
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Redis connected: %s", self.redis_url)
        except ImportError:
            logger.warning("redis package not installed, falling back to in-memory store")
        except Exception as e:
            logger.warning("Redis connection failed (%s), falling back to in-memory store", e)
            self._redis = None

    async def close(self) -> None:
        """关闭Redis状态。"""
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")

    async def save_snapshot(
        self,
        correlation_id: str,
        version: int,
        snapshot: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """保存快照。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。
            version: 资源版本号。
            snapshot: 快照。
            ttl: 输入参数。
        """
        key = self._make_key(correlation_id, version)
        value = json.dumps(snapshot, ensure_ascii=False, default=str)
        expire = ttl if ttl is not None else self.default_ttl

        if self._redis:
            if expire > 0:
                await self._redis.setex(key, expire, value)
            else:
                await self._redis.set(key, value)
        else:
            self._fallback[key] = value

        logger.debug(
            "Snapshot saved (key=%s, version=%d, ttl=%s)",
            key,
            version,
            expire,
        )

    async def load_snapshot(
        self,
        correlation_id: str,
        version: int,
    ) -> dict[str, Any] | None:
        """加载快照。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。
            version: 资源版本号。

        Returns:
            结构化结果字典。
        """
        key = self._make_key(correlation_id, version)

        if self._redis:
            value = await self._redis.get(key)
        else:
            value = self._fallback.get(key)

        if value is None:
            return None

        return json.loads(value)

    async def load_latest_snapshot(
        self,
        correlation_id: str,
    ) -> dict[str, Any] | None:
        """加载最新的上下文快照。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。

        Returns:
            结构化结果字典。
        """
        versions: list[tuple[int, str]] = []
        if self._redis:
            pattern = f"{self.key_prefix}:{correlation_id}:*"
            keys = await self._redis.keys(pattern)
            if not keys:
                return None

            for k in keys:
                parts = k.split(":")
                ver = int(parts[-1])
                versions.append((ver, k))
            versions.sort(key=lambda x: x[0], reverse=True)

            value = await self._redis.get(versions[0][1])
            return json.loads(value) if value else None
        else:
            prefix = f"{self.key_prefix}:{correlation_id}:"
            for k, v in self._fallback.items():
                if k.startswith(prefix):
                    ver = int(k.split(":")[-1])
                    versions.append((ver, v))
            if not versions:
                return None
            versions.sort(key=lambda x: x[0], reverse=True)
            return json.loads(versions[0][1])

    async def delete_snapshots(self, correlation_id: str) -> int:
        """删除指定工作流的所有快照。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。

        Returns:
            整数结果。
        """
        if self._redis:
            pattern = f"{self.key_prefix}:{correlation_id}:*"
            keys = await self._redis.keys(pattern)
            if keys:
                await self._redis.delete(*keys)
            return len(keys)
        else:
            prefix = f"{self.key_prefix}:{correlation_id}:"
            keys_to_delete = [k for k in self._fallback if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._fallback[k]
            return len(keys_to_delete)

    def _make_key(self, correlation_id: str, version: int) -> str:
        """构造键。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。
            version: 资源版本号。

        Returns:
            字符串结果。
        """
        return f"{self.key_prefix}:{correlation_id}:{version}"
