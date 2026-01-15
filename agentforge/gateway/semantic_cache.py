"""AgentForge 模型网关层：semantic_cache。

本模块负责 semantic_cache 相关能力，是 模型网关层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：CacheEntry、SemanticCache。
"""

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
    """CacheEntry。

    CacheEntry 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - key: str。
    - embedding: list[float]。
    - result: dict。
    - hit_count: int。
    - created_at: float。
    - last_accessed: float。
    - 方法 age_hours()。
    - 方法 idle_minutes()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    key: str  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    embedding: list[float]  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    result: dict  # 缓存处理。
    hit_count: int = 0  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    @property
    def age_hours(self) -> float:
        """执行 age_hours 对应的逻辑，并返回处理结果。

        Returns:
            float，函数执行后的结果。
        """
        return (time.time() - self.created_at) / 3600

    @property
    def idle_minutes(self) -> float:
        """执行 idle_minutes 对应的逻辑，并返回处理结果。

        Returns:
            float，函数执行后的结果。
        """
        return (time.time() - self.last_accessed) / 60


class SemanticCache:
    """SemanticCache。

    SemanticCache 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - DEFAULT_THRESHOLD: 0.92。
    - DEFAULT_MAX_SIZE: 10000。
    - DEFAULT_TTL_HOURS: 24。
    - 方法 get()。
    - 方法 put()。
    - 方法 stats()。
    - 方法 clear()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    DEFAULT_THRESHOLD = 0.92
    DEFAULT_MAX_SIZE = 10000
    DEFAULT_TTL_HOURS = 24

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        max_size: int = DEFAULT_MAX_SIZE,
        ttl_hours: float = DEFAULT_TTL_HOURS,
    ):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            threshold: float，调用方传入的 threshold 参数。
            max_size: int，调用方传入的 max_size 参数。
            ttl_hours: float，调用方传入的 ttl_hours 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._threshold = threshold
        self._max_size = max_size
        self._ttl_hours = ttl_hours

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._total_lookups = 0
        self._total_hits = 0
        self._total_evictions = 0

    async def get(self, query_embedding: list[float]) -> Optional[CacheEntry]:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            query_embedding: list[float]，调用方传入的 query_embedding 参数。

        Returns:
            Optional[CacheEntry]，函数执行后的结果。
        """
        async with self._lock:
            self._total_lookups += 1

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
                # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
        """执行 put 对应的逻辑，并返回处理结果。

        Args:
            key_text: str，调用方传入的 key_text 参数。
            embedding: list[float]，调用方传入的 embedding 参数。
            result: dict，调用方传入的 result 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            if len(self._store) >= self._max_size:
                await self._evict()

            key = key_text[:200]  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            if key in self._store:
                del self._store[key]

            entry = CacheEntry(
                key=key,
                embedding=embedding,
                result=result,
            )
            self._store[key] = entry

    async def _evict(self) -> None:
        """执行 _evict 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        now = time.time()
        ttl_seconds = self._ttl_hours * 3600

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        expired_keys = [
            key for key, entry in self._store.items() if (now - entry.created_at) > ttl_seconds
        ]
        for key in expired_keys:
            del self._store[key]
        self._total_evictions += len(expired_keys)

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        if len(self._store) >= self._max_size:
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            evict_count = max(1, self._max_size // 10)
            for _ in range(evict_count):
                if self._store:
                    self._store.popitem(last=False)
                    self._total_evictions += 1

    @staticmethod
    def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """执行 _cosine_similarity 对应的逻辑，并返回处理结果。

        Args:
            v1: list[float]，调用方传入的 v1 参数。
            v2: list[float]，调用方传入的 v2 参数。

        Returns:
            float，函数执行后的结果。
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
        """执行 stats 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
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
        """执行 clear 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            self._store.clear()
            self._total_lookups = 0
            self._total_hits = 0
            self._total_evictions = 0
