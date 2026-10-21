"""记忆模块。"""

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class MemoryConfig:
    """记忆配置模型。

    Attributes:
        enable_working: 工作。
        enable_short_term: 短期期限。
        enable_long_term: 长期期限。
        max_working_items: 最大工作条目。
        max_short_term_items: 最大短期期限条目。
        max_long_term_items: 最大长期期限条目。
        long_term_collection: 长期期限。
    """

    enable_working: bool = True
    enable_short_term: bool = True
    enable_long_term: bool = False
    max_working_items: int = 20
    max_short_term_items: int = 200
    max_long_term_items: int = 50000
    long_term_collection: str = "default"


class WorkingMemory:
    """工作记忆，保存当前任务执行期间的临时上下文。"""

    def __init__(self, max_items: int = 20):
        """初始化 WorkingMemory。

        Args:
            max_items: 最大条目。
        """
        self._store: OrderedDict[str, Any] = OrderedDict()
        self._max_items = max_items
        self._lock = asyncio.Lock()

    async def write(self, key: str, value: Any) -> None:
        """写入工作。

        Args:
            key: 缓存或配置键。
            value: 待处理值。
        """
        async with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = value
            while len(self._store) > self._max_items:
                self._store.popitem(last=False)

    async def read(self, key: str) -> Optional[Any]:
        """读取工作。

        Args:
            key: 缓存或配置键。

        Returns:
            处理结果对象。
        """
        async with self._lock:
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            return self._store[key]

    async def get_all(self) -> dict[str, Any]:
        """获取全部。

        Returns:
            结构化结果字典。
        """
        async with self._lock:
            return dict(self._store)

    async def clear(self) -> None:
        """清空工作。"""
        async with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        """返回大小。

        Returns:
            整数结果。
        """
        return len(self._store)


class ShortTermMemory:
    """短期记忆，保存近期会话和任务状态。"""

    def __init__(self, session_id: str, max_items: int = 200):
        """初始化 ShortTermMemory。

        Args:
            session_id: 会话 ID。
            max_items: 最大条目。
        """
        self._session_id = session_id
        self._store: dict[str, dict] = {}
        self._max_items = max_items
        self._lock = asyncio.Lock()

    async def write(self, key: str, value: Any) -> None:
        """写入短期期限。

        Args:
            key: 缓存或配置键。
            value: 待处理值。
        """
        async with self._lock:
            now = time.time()
            self._store[key] = {
                "value": value,
                "created_at": now,
                "last_accessed": now,
                "access_count": 0,
            }
            if len(self._store) > self._max_items:
                await self._evict_lru()

    async def read(self, key: str) -> Optional[Any]:
        """读取短期期限。

        Args:
            key: 缓存或配置键。

        Returns:
            处理结果对象。
        """
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            entry["last_accessed"] = time.time()
            entry["access_count"] += 1
            return entry["value"]

    async def delete(self, key: str) -> bool:
        """删除短期期限。

        Args:
            key: 缓存或配置键。

        Returns:
            操作是否成功。
        """
        async with self._lock:
            return self._store.pop(key, None) is not None

    async def _evict_lru(self) -> None:
        """淘汰LRU。"""
        if not self._store:
            return
        lru_key = min(self._store, key=lambda k: self._store[k]["last_accessed"])
        del self._store[lru_key]

    async def clear(self) -> None:
        """清空短期期限。"""
        async with self._lock:
            self._store.clear()

    @property
    def session_id(self) -> str:
        """返回会话ID。

        Returns:
            字符串结果。
        """
        return self._session_id

    @property
    def size(self) -> int:
        """返回大小。

        Returns:
            整数结果。
        """
        return len(self._store)


class LongTermMemory:
    """长期记忆，持久化跨会话知识。"""

    def __init__(self, collection: str = "default", max_items: int = 50000):
        """初始化 LongTermMemory。

        Args:
            collection: 输入参数。
            max_items: 最大条目。
        """
        self._collection = collection
        self._max_items = max_items
        self._vectors: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def store(
        self,
        key: str,
        text: str,
        embedding: list[float],
        metadata: Optional[dict] = None,
    ) -> None:
        """保存当前记录。

        Args:
            key: 缓存或配置键。
            text: 待处理文本。
            embedding: 输入参数。
            metadata: 附加元数据。
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
        """搜索与查询条件匹配的数据。

        Args:
            query_embedding: 查询。
            top_k: 返回结果数量上限。
            min_similarity: 相似度。

        Returns:
            结果列表。
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

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def delete(self, key: str) -> bool:
        """删除长期期限。

        Args:
            key: 缓存或配置键。

        Returns:
            操作是否成功。
        """
        async with self._lock:
            return self._vectors.pop(key, None) is not None

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
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sum(a * a for a in v1) ** 0.5
        norm2 = sum(b * b for b in v2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    @property
    def size(self) -> int:
        """返回大小。

        Returns:
            整数结果。
        """
        return len(self._vectors)


class MemoryManager:
    """统一管理三级记忆的读写、检索和淘汰。"""

    def __init__(
        self,
        config: MemoryConfig,
        session_id: str = "default",
    ):
        """初始化 MemoryManager。

        Args:
            config: 组件配置。
            session_id: 会话 ID。
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
        """读取记忆管理器。

        Args:
            level: 级别。
            key: 缓存或配置键。

        Returns:
            处理结果对象。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if level == "working" and self.working:
            return await self.working.read(key)
        elif level == "short_term" and self.short_term:
            return await self.short_term.read(key)
        elif level == "long_term":
            raise ValueError("Use search() for long-term memory retrieval")
        return None

    async def write(self, level: str, key: str, value: Any, **kwargs) -> None:
        """写入记忆管理器。

        Args:
            level: 级别。
            key: 缓存或配置键。
            value: 待处理值。
            kwargs: 关键字参数。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
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
        """搜索与查询条件匹配的数据。

        Args:
            query_embedding: 查询。
            top_k: 返回结果数量上限。

        Returns:
            结果列表。
        """
        if not self.long_term:
            return []
        return await self.long_term.search(query_embedding, top_k=top_k)

    async def clear_working(self) -> None:
        """清空工作。"""
        if self.working:
            await self.working.clear()

    async def clear_session(self) -> None:
        """清空会话。"""
        if self.working:
            await self.working.clear()
        if self.short_term:
            await self.short_term.clear()
