"""AgentForge 核心运行时层：context_store。

本模块负责 context_store 相关能力，是 核心运行时层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：ContextStore。
"""

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ContextStore:
    """ContextStore。

    ContextStore 负责数据读写，保持事务一致性、隔离约束和存储细节封装。

    主要成员：
    - 方法 initialize()。
    - 方法 write()。
    - 方法 read()。
    - 方法 read_with_mapping()。
    - 方法 get_all()。
    - 方法 get_input()。
    - 方法 has()。
    - 方法 delete()。
    - 方法 clear()。
    - 方法 size()。
    - 方法 log_access()。
    - 方法 get_access_log()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._store: dict[str, Any] = {}
        self._input: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._access_log: list[dict] = []  # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    async def initialize(self, input_data: dict) -> None:
        """执行 initialize 对应的逻辑，并返回处理结果。

        Args:
            input_data: dict，调用方传入的 input_data 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            self._input = dict(input_data)
            logger.debug("ContextStore initialized with %d input fields", len(input_data))

    async def write(self, key: str, value: Any) -> None:
        """执行 write 对应的逻辑，并返回处理结果。

        Args:
            key: str，调用方传入的 key 参数。
            value: Any，调用方传入的 value 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            self._store[key] = value

    async def read(self, key: str) -> Optional[Any]:
        """执行 read 对应的逻辑，并返回处理结果。

        Args:
            key: str，调用方传入的 key 参数。

        Returns:
            Optional[Any]，函数执行后的结果。
        """
        async with self._lock:
            return self._store.get(key)

    async def read_with_mapping(self, input_mapping: dict[str, str]) -> dict[str, Any]:
        """执行 read_with_mapping 对应的逻辑，并返回处理结果。

        Args:
            input_mapping: dict[str, str]，调用方传入的 input_mapping 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
        """
        async with self._lock:
            resolved = {}
            for target, ref in input_mapping.items():
                if ref.startswith("$ctx."):
                    ctx_key = ref[5:]  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                    resolved[target] = self._store.get(ctx_key)
                    if ctx_key not in self._store:
                        logger.debug(
                            "ContextStore: $ctx.%s not found for param '%s'", ctx_key, target
                        )
                elif ref.startswith("$input."):
                    input_key = ref[7:]  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                    resolved[target] = self._input.get(input_key)
                    if input_key not in self._input:
                        logger.debug(
                            "ContextStore: $input.%s not found for param '%s'", input_key, target
                        )
                else:
                    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                    resolved[target] = ref
            return resolved

    async def get_all(self) -> dict[str, Any]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            dict[str, Any]，函数执行后的结果。
        """
        async with self._lock:
            return dict(self._store)

    async def get_input(self) -> dict[str, Any]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            dict[str, Any]，函数执行后的结果。
        """
        async with self._lock:
            return dict(self._input)

    async def has(self, key: str) -> bool:
        """执行 has 对应的逻辑，并返回处理结果。

        Args:
            key: str，调用方传入的 key 参数。

        Returns:
            bool，函数执行后的结果。
        """
        async with self._lock:
            return key in self._store

    async def delete(self, key: str) -> bool:
        """执行 delete 对应的核心操作，并保持调用契约稳定。

        Args:
            key: str，调用方传入的 key 参数。

        Returns:
            bool，函数执行后的结果。
        """
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def clear(self) -> None:
        """执行 clear 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            self._store.clear()
            self._access_log.clear()
            logger.debug("ContextStore cleared")

    def size(self) -> int:
        """执行 size 对应的逻辑，并返回处理结果。

        Returns:
            int，函数执行后的结果。
        """
        return len(self._store)

    async def log_access(self, node_id: str, keys_read: list[str]) -> None:
        """执行 log_access 对应的逻辑，并返回处理结果。

        Args:
            node_id: str，调用方传入的 node_id 参数。
            keys_read: list[str]，调用方传入的 keys_read 参数。

        Returns:
            None，函数执行后的结果。
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
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            list[dict]，函数执行后的结果。
        """
        async with self._lock:
            return list(self._access_log)
