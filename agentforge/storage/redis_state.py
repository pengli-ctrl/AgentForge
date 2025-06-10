"""RedisStateStore — Redis 状态存储封装。

作为 Context Snapshot 的持久化后端，提供高速的上下文快照读写。
在生产环境中，Context Snapshot 通过 Redis 持久化，确保服务重启后状态可恢复。

V2 → V3 迁移说明：
    V2 使用 Redis 共享状态（context 字典无限膨胀的根源）。
    V3 使用 Context Snapshot 隔离 + Redis 作为快照持久化后端。
    Redis 的角色从"共享可变状态"变为"不可变快照存储"。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class RedisStateStore:
    """Redis 状态存储封装 — Context Snapshot 的持久化后端。

    提供快照的保存、加载、删除和 TTL 管理功能。
    当 Redis 不可用时，自动回退到内存存储。

    Args:
        redis_url: Redis 连接地址。
        key_prefix: Key 前缀（用于命名空间隔离）。
        default_ttl: 默认 TTL（秒），0 表示不过期。
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "agentforge:snapshot",
        default_ttl: int = 86400,
    ) -> None:
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self._redis: Any = None
        self._fallback: dict[str, str] = {}

    async def connect(self) -> None:
        """连接 Redis 服务。

        连接失败时记录警告，自动回退到内存存储。
        """
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
        """关闭 Redis 连接。"""
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
        """保存上下文快照到 Redis。

        Args:
            correlation_id: 工作流关联 ID。
            version: 快照版本号。
            snapshot: 快照数据。
            ttl: TTL（秒），None 使用默认值。
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
        """从 Redis 加载上下文快照。

        Args:
            correlation_id: 工作流关联 ID。
            version: 快照版本号。

        Returns:
            快照数据字典，不存在则返回 None。
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

        通过扫描版本号找到最新版本。

        Args:
            correlation_id: 工作流关联 ID。

        Returns:
            最新版本的快照数据，不存在则返回 None。
        """
        if self._redis:
            pattern = f"{self.key_prefix}:{correlation_id}:*"
            keys = await self._redis.keys(pattern)
            if not keys:
                return None

            versions: list[tuple[int, str]] = []
            for k in keys:
                parts = k.split(":")
                ver = int(parts[-1])
                versions.append((ver, k))
            versions.sort(key=lambda x: x[0], reverse=True)

            value = await self._redis.get(versions[0][1])
            return json.loads(value) if value else None
        else:
            prefix = f"{self.key_prefix}:{correlation_id}:"
            versions: list[tuple[int, str]] = []
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
            correlation_id: 工作流关联 ID。

        Returns:
            删除的快照数量。
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
        """构造 Redis Key。

        Args:
            correlation_id: 工作流关联 ID。
            version: 快照版本号。

        Returns:
            格式为 "agentforge:snapshot:{correlation_id}:{version}" 的 Key。
        """
        return f"{self.key_prefix}:{correlation_id}:{version}"
