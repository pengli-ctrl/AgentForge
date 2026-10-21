"""上下文存储模块。"""

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ContextStore:
    """上下文领域组件。"""

    def __init__(self):
        """初始化 ContextStore。"""
        self._store: dict[str, Any] = {}
        self._input: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._access_log: list[dict] = []

    async def initialize(self, input_data: dict) -> None:
        """初始化上下文。

        Args:
            input_data: 输入数据。
        """
        async with self._lock:
            self._input = dict(input_data)
            logger.debug("ContextStore initialized with %d input fields", len(input_data))

    async def write(self, key: str, value: Any) -> None:
        """写入上下文。

        Args:
            key: 缓存或配置键。
            value: 待处理值。
        """
        async with self._lock:
            self._store[key] = value

    async def read(self, key: str) -> Optional[Any]:
        """读取上下文。

        Args:
            key: 缓存或配置键。

        Returns:
            处理结果对象。
        """
        async with self._lock:
            return self._store.get(key)

    async def read_with_mapping(self, input_mapping: dict[str, str]) -> dict[str, Any]:
        """读取使用映射。

        Args:
            input_mapping: 输入。

        Returns:
            结构化结果字典。
        """
        async with self._lock:
            resolved = {}
            for target, ref in input_mapping.items():
                if ref.startswith("$ctx."):
                    ctx_key = ref[5:]
                    resolved[target] = self._store.get(ctx_key)
                    if ctx_key not in self._store:
                        logger.debug(
                            "ContextStore: $ctx.%s not found for param '%s'", ctx_key, target
                        )
                elif ref.startswith("$input."):
                    input_key = ref[7:]
                    resolved[target] = self._input.get(input_key)
                    if input_key not in self._input:
                        logger.debug(
                            "ContextStore: $input.%s not found for param '%s'", input_key, target
                        )
                else:
                    resolved[target] = ref
            return resolved

    async def get_all(self) -> dict[str, Any]:
        """获取全部。

        Returns:
            结构化结果字典。
        """
        async with self._lock:
            return dict(self._store)

    async def get_input(self) -> dict[str, Any]:
        """获取输入。

        Returns:
            结构化结果字典。
        """
        async with self._lock:
            return dict(self._input)

    async def has(self, key: str) -> bool:
        """判断指定键或名称是否存在。

        Args:
            key: 缓存或配置键。

        Returns:
            操作是否成功。
        """
        async with self._lock:
            return key in self._store

    async def delete(self, key: str) -> bool:
        """删除上下文。

        Args:
            key: 缓存或配置键。

        Returns:
            操作是否成功。
        """
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def clear(self) -> None:
        """清空上下文。"""
        async with self._lock:
            self._store.clear()
            self._access_log.clear()
            logger.debug("ContextStore cleared")

    def size(self) -> int:
        """获取大小上下文。

        Returns:
            整数结果。
        """
        return len(self._store)

    async def log_access(self, node_id: str, keys_read: list[str]) -> None:
        """记录访问。

        Args:
            node_id: 节点 ID。
            keys_read: 键读取。
        """
        async with self._lock:
            self._access_log.append(
                {
                    "node_id": node_id,
                    "keys_read": keys_read,
                    "store_size": len(self._store),
                }
            )

    async def get_access_log(self) -> list[dict]:
        """获取访问日志。

        Returns:
            结果列表。
        """
        async with self._lock:
            return list(self._access_log)
