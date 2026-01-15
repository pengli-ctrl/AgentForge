"""AgentForge 核心运行时层：memory。

本模块负责 memory 相关能力，是 核心运行时层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：MemoryConfig、WorkingMemory、ShortTermMemory、LongTermMemory、MemoryManager。
"""

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class MemoryConfig:
    """MemoryConfig。

    MemoryConfig 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - enable_working: bool。
    - enable_short_term: bool。
    - enable_long_term: bool。
    - max_working_items: int。
    - max_short_term_items: int。
    - max_long_term_items: int。
    - long_term_collection: str。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    enable_working: bool = True
    enable_short_term: bool = True
    enable_long_term: bool = False
    max_working_items: int = 20  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    max_short_term_items: int = 200  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    max_long_term_items: int = 50000  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    long_term_collection: str = "default"  # 说明：该步骤用于实现上述逻辑并保证行为稳定。


class WorkingMemory:
    """WorkingMemory。

    WorkingMemory 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 write()。
    - 方法 read()。
    - 方法 get_all()。
    - 方法 clear()。
    - 方法 size()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self, max_items: int = 20):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            max_items: int，调用方传入的 max_items 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._store: OrderedDict[str, Any] = OrderedDict()
        self._max_items = max_items
        self._lock = asyncio.Lock()

    async def write(self, key: str, value: Any) -> None:
        """执行 write 对应的逻辑，并返回处理结果。

        Args:
            key: str，调用方传入的 key 参数。
            value: Any，调用方传入的 value 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = value
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            while len(self._store) > self._max_items:
                self._store.popitem(last=False)

    async def read(self, key: str) -> Optional[Any]:
        """执行 read 对应的逻辑，并返回处理结果。

        Args:
            key: str，调用方传入的 key 参数。

        Returns:
            Optional[Any]，函数执行后的结果。
        """
        async with self._lock:
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            return self._store[key]

    async def get_all(self) -> dict[str, Any]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            dict[str, Any]，函数执行后的结果。
        """
        async with self._lock:
            return dict(self._store)

    async def clear(self) -> None:
        """执行 clear 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        """执行 size 对应的逻辑，并返回处理结果。

        Returns:
            int，函数执行后的结果。
        """
        return len(self._store)


class ShortTermMemory:
    """ShortTermMemory。

    ShortTermMemory 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 write()。
    - 方法 read()。
    - 方法 delete()。
    - 方法 clear()。
    - 方法 session_id()。
    - 方法 size()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self, session_id: str, max_items: int = 200):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            session_id: str，调用方传入的 session_id 参数。
            max_items: int，调用方传入的 max_items 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._session_id = session_id
        self._store: dict[str, dict] = {}  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._max_items = max_items
        self._lock = asyncio.Lock()

    async def write(self, key: str, value: Any) -> None:
        """执行 write 对应的逻辑，并返回处理结果。

        Args:
            key: str，调用方传入的 key 参数。
            value: Any，调用方传入的 value 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            now = time.time()
            self._store[key] = {
                "value": value,
                "created_at": now,
                "last_accessed": now,
                "access_count": 0,
            }
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            if len(self._store) > self._max_items:
                await self._evict_lru()

    async def read(self, key: str) -> Optional[Any]:
        """执行 read 对应的逻辑，并返回处理结果。

        Args:
            key: str，调用方传入的 key 参数。

        Returns:
            Optional[Any]，函数执行后的结果。
        """
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            entry["last_accessed"] = time.time()
            entry["access_count"] += 1
            return entry["value"]

    async def delete(self, key: str) -> bool:
        """执行 delete 对应的核心操作，并保持调用契约稳定。

        Args:
            key: str，调用方传入的 key 参数。

        Returns:
            bool，函数执行后的结果。
        """
        async with self._lock:
            return self._store.pop(key, None) is not None

    async def _evict_lru(self) -> None:
        """执行 _evict_lru 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        if not self._store:
            return
        lru_key = min(self._store, key=lambda k: self._store[k]["last_accessed"])
        del self._store[lru_key]

    async def clear(self) -> None:
        """执行 clear 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            self._store.clear()

    @property
    def session_id(self) -> str:
        """执行 session_id 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
        """
        return self._session_id

    @property
    def size(self) -> int:
        """执行 size 对应的逻辑，并返回处理结果。

        Returns:
            int，函数执行后的结果。
        """
        return len(self._store)


class LongTermMemory:
    """LongTermMemory。

    LongTermMemory 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 store()。
    - 方法 search()。
    - 方法 delete()。
    - 方法 size()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self, collection: str = "default", max_items: int = 50000):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            collection: str，调用方传入的 collection 参数。
            max_items: int，调用方传入的 max_items 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._collection = collection
        self._max_items = max_items
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._vectors: dict[str, dict] = {}  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._lock = asyncio.Lock()

    async def store(
        self,
        key: str,
        text: str,
        embedding: list[float],
        metadata: Optional[dict] = None,
    ) -> None:
        """执行 store 对应的逻辑，并返回处理结果。

        Args:
            key: str，调用方传入的 key 参数。
            text: str，调用方传入的 text 参数。
            embedding: list[float]，调用方传入的 embedding 参数。
            metadata: Optional[dict]，调用方传入的 metadata 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            self._vectors[key] = {
                "text": text,
                "embedding": embedding,
                "metadata": metadata or {},
                "created_at": time.time(),
            }

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        min_similarity: float = 0.7,
    ) -> list[dict]:
        """执行 search 对应的核心操作，并保持调用契约稳定。

        Args:
            query_embedding: list[float]，调用方传入的 query_embedding 参数。
            top_k: int，调用方传入的 top_k 参数。
            min_similarity: float，调用方传入的 min_similarity 参数。

        Returns:
            list[dict]，函数执行后的结果。
        """
        async with self._lock:
            results = []
            for key, doc in self._vectors.items():
                score = self._cosine_similarity(query_embedding, doc["embedding"])
                if score >= min_similarity:
                    results.append(
                        {
                            "key": key,
                            "text": doc["text"],
                            "score": score,
                            "metadata": doc["metadata"],
                        }
                    )

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def delete(self, key: str) -> bool:
        """执行 delete 对应的核心操作，并保持调用契约稳定。

        Args:
            key: str，调用方传入的 key 参数。

        Returns:
            bool，函数执行后的结果。
        """
        async with self._lock:
            return self._vectors.pop(key, None) is not None

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
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sum(a * a for a in v1) ** 0.5
        norm2 = sum(b * b for b in v2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    @property
    def size(self) -> int:
        """执行 size 对应的逻辑，并返回处理结果。

        Returns:
            int，函数执行后的结果。
        """
        return len(self._vectors)


class MemoryManager:
    """MemoryManager。

    MemoryManager 是核心运行时组件，负责状态管理、调度和跨模块协作。

    主要成员：
    - 方法 read()。
    - 方法 write()。
    - 方法 search()。
    - 方法 clear_working()。
    - 方法 clear_session()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(
        self,
        config: MemoryConfig,
        session_id: str = "default",
    ):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            config: MemoryConfig，调用方传入的 config 参数。
            session_id: str，调用方传入的 session_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._config = config
        self.working = (
            WorkingMemory(max_items=config.max_working_items) if config.enable_working else None
        )
        self.short_term = (
            ShortTermMemory(session_id, max_items=config.max_short_term_items)
            if config.enable_short_term
            else None
        )
        self.long_term = (
            LongTermMemory(config.long_term_collection, max_items=config.max_long_term_items)
            if config.enable_long_term
            else None
        )

    async def read(self, level: str, key: str) -> Optional[Any]:
        """执行 read 对应的逻辑，并返回处理结果。

        Args:
            level: str，调用方传入的 level 参数。
            key: str，调用方传入的 key 参数。

        Returns:
            Optional[Any]，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if level == "working" and self.working:
            return await self.working.read(key)
        elif level == "short_term" and self.short_term:
            return await self.short_term.read(key)
        elif level == "long_term":
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            raise ValueError("Use search() for long-term memory retrieval")
        return None

    async def write(self, level: str, key: str, value: Any, **kwargs) -> None:
        """执行 write 对应的逻辑，并返回处理结果。

        Args:
            level: str，调用方传入的 level 参数。
            key: str，调用方传入的 key 参数。
            value: Any，调用方传入的 value 参数。
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if level == "working" and self.working:
            await self.working.write(key, value)
        elif level == "short_term" and self.short_term:
            await self.short_term.write(key, value)
        elif level == "long_term" and self.long_term:
            await self.long_term.store(
                key=key,
                text=kwargs.get("text", str(value)),
                embedding=kwargs.get("embedding", []),
                metadata=kwargs.get("metadata"),
            )
        else:
            raise ValueError(f"Memory tier '{level}' is not enabled")

    async def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        """执行 search 对应的核心操作，并保持调用契约稳定。

        Args:
            query_embedding: list[float]，调用方传入的 query_embedding 参数。
            top_k: int，调用方传入的 top_k 参数。

        Returns:
            list[dict]，函数执行后的结果。
        """
        if not self.long_term:
            return []
        return await self.long_term.search(query_embedding, top_k=top_k)

    async def clear_working(self) -> None:
        """执行 clear_working 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        if self.working:
            await self.working.clear()

    async def clear_session(self) -> None:
        """执行 clear_session 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        if self.working:
            await self.working.clear()
        if self.short_term:
            await self.short_term.clear()
