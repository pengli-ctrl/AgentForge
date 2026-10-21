"""缓存模块。"""

import asyncio
import logging
import math
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目相关组件。

    Attributes:
        key: 键。
        embedding: 字段值。
        result: 处理结果。
        hit_count: 数量。
        created_at: 创建时间。
        last_accessed: 字段值。
    """

    key: str
    embedding: list[float]
    result: dict  # 缓存处理。
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    @property
    def age_hours(self) -> float:
        """计算存在小时数。

        Returns:
            数值结果。
        """
        return (time.time() - self.created_at) / 3600

    @property
    def idle_minutes(self) -> float:
        """计算空闲分钟数。

        Returns:
            数值结果。
        """
        return (time.time() - self.last_accessed) / 60


class SemanticCache:
    """缓存实现。"""

    DEFAULT_THRESHOLD = 0.92
    DEFAULT_MAX_SIZE = 10000
    DEFAULT_TTL_HOURS = 24

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        max_size: int = DEFAULT_MAX_SIZE,
        ttl_hours: float = DEFAULT_TTL_HOURS,
    ):
        """初始化 SemanticCache。

        Args:
            threshold: 阈值。
            max_size: 最大大小。
            ttl_hours: 输入参数。
        """
        self._threshold = threshold
        self._max_size = max_size
        self._ttl_hours = ttl_hours

        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()

        self._total_lookups = 0
        self._total_hits = 0
        self._total_evictions = 0

    async def get(self, query_embedding: list[float]) -> Optional[CacheEntry]:
        """获取缓存。

        Args:
            query_embedding: 查询。

        Returns:
            处理结果对象。
        """
        async with self._lock:
            self._total_lookups += 1

            expired_keys = [
                key for key, entry in self._store.items() if entry.age_hours > self._ttl_hours
            ]
            if expired_keys:
                for key in expired_keys:
                    del self._store[key]
                self._total_evictions += len(expired_keys)

            best_entry: Optional[CacheEntry] = None
            best_score = 0.0

            for entry in self._store.values():
                score = self._cosine_similarity(query_embedding, entry.embedding)
                if score > best_score:
                    best_score = score
                    best_entry = entry

            if best_entry is not None and best_score >= self._threshold:
                # 缓存处理。
                best_entry.hit_count += 1
                best_entry.last_accessed = time.time()
                self._store.move_to_end(best_entry.key)
                self._total_hits += 1

                logger.debug(
                    "Cache HIT: score=%.4f, key='%s', hit_count=%d",
                    best_score,
                    best_entry.key[:50],
                    best_entry.hit_count,
                )
                return best_entry
            else:
                logger.debug(
                    "Cache MISS: best_score=%.4f < threshold=%.4f",
                    best_score,
                    self._threshold,
                )
                return None

    async def put(
        self,
        key_text: str,
        embedding: list[float],
        result: dict,
    ) -> None:
        """写入缓存或对象存储数据。

        Args:
            key_text: 键文本。
            embedding: 输入参数。
            result: 处理结果。
        """
        async with self._lock:
            if len(self._store) >= self._max_size:
                await self._evict()

            key = key_text[:200]
            if key in self._store:
                del self._store[key]

            entry = CacheEntry(
                key=key,
                embedding=embedding,
                result=result,
            )
            self._store[key] = entry

    async def _evict(self) -> None:
        """淘汰缓存。"""
        now = time.time()
        ttl_seconds = self._ttl_hours * 3600

        expired_keys = [
            key for key, entry in self._store.items() if (now - entry.created_at) > ttl_seconds
        ]
        for key in expired_keys:
            del self._store[key]
        self._total_evictions += len(expired_keys)

        if len(self._store) >= self._max_size:
            evict_count = max(1, self._max_size // 10)
            for _ in range(evict_count):
                if self._store:
                    self._store.popitem(last=False)
                    self._total_evictions += 1

    @staticmethod
    def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """计算两个向量的余弦相似度。

        Args:
            v1: 输入参数。
            v2: 输入参数。

        Returns:
            数值结果。
        """
        if len(v1) != len(v2) or not v1:
            return 0.0

        dot_product = 0.0
        norm1 = 0.0
        norm2 = 0.0

        for a, b in zip(v1, v2):
            dot_product += a * b
            norm1 += a * a
            norm2 += b * b

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (math.sqrt(norm1) * math.sqrt(norm2))

    def stats(self) -> dict:
        """获取当前统计数据。

        Returns:
            结构化结果字典。
        """
        hit_rate = self._total_hits / self._total_lookups if self._total_lookups > 0 else 0.0
        return {
            "total_lookups": self._total_lookups,
            "total_hits": self._total_hits,
            "hit_rate": round(hit_rate, 4),
            "current_size": len(self._store),
            "max_size": self._max_size,
            "total_evictions": self._total_evictions,
            "threshold": self._threshold,
            "ttl_hours": self._ttl_hours,
            "utilization": round(len(self._store) / self._max_size, 4) if self._max_size > 0 else 0,
        }

    async def clear(self) -> None:
        """清空缓存。"""
        async with self._lock:
            self._store.clear()
            self._total_lookups = 0
            self._total_hits = 0
            self._total_evictions = 0
