"""AgentForge 核心运行时层：agent_registry。

本模块负责 agent_registry 相关能力，是 核心运行时层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：AgentRegistry。
"""

import logging
from typing import Optional, Type

from agentforge.core.agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """AgentRegistry。

    AgentRegistry 是核心运行时组件，负责状态管理、调度和跨模块协作。

    主要成员：
    - 方法 register()。
    - 方法 register_instance()。
    - 方法 get()。
    - 方法 unregister()。
    - 方法 list_agents()。
    - 方法 get_agent_info()。
    - 方法 get_all_stats()。
    - 方法 reset_all()。
    - 方法 count()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._classes: dict[str, Type[BaseAgent]] = {}
        self._instances: dict[str, BaseAgent] = {}
        self._metadata: dict[str, dict] = {}  # Agent 注册与查询。
        import asyncio

        self._lock = asyncio.Lock()

    async def register(
        self,
        name: str,
        agent_class: Type[BaseAgent],
        metadata: Optional[dict] = None,
    ) -> None:
        """执行 register 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。
            agent_class: Type[BaseAgent]，调用方传入的 agent_class 参数。
            metadata: Optional[dict]，调用方传入的 metadata 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
            KeyError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if not issubclass(agent_class, BaseAgent):
            raise ValueError(
                f"Cannot register '{name}': {agent_class.__name__} "
                f"is not a subclass of BaseAgent"
            )

        async with self._lock:
            if name in self._classes or name in self._instances:
                raise KeyError(f"Agent '{name}' is already registered")

            self._classes[name] = agent_class
            self._metadata[name] = metadata or {}
            logger.info("Registered agent class: %s → %s", name, agent_class.__name__)

    async def register_instance(
        self,
        name: str,
        agent: BaseAgent,
        metadata: Optional[dict] = None,
    ) -> None:
        """执行 register_instance 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。
            agent: BaseAgent，调用方传入的 agent 参数。
            metadata: Optional[dict]，调用方传入的 metadata 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
            KeyError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if not isinstance(agent, BaseAgent):
            raise ValueError(f"Cannot register '{name}': instance is not a BaseAgent")

        async with self._lock:
            if name in self._classes or name in self._instances:
                raise KeyError(f"Agent '{name}' is already registered")

            self._instances[name] = agent
            self._metadata[name] = metadata or {}
            logger.info("Registered agent instance: %s", name)

    async def get(self, name: str) -> BaseAgent:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            name: str，调用方传入的 name 参数。

        Returns:
            BaseAgent，函数执行后的结果。

        Raises:
            KeyError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        async with self._lock:
            # 就绪状态。
            if name in self._instances:
                return self._instances[name]

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            if name in self._classes:
                agent_class = self._classes[name]
                instance = agent_class(name=name)
                self._instances[name] = instance
                logger.info("Lazy-initialized agent: %s", name)
                return instance

            raise KeyError(f"Agent '{name}' is not registered")

    async def unregister(self, name: str) -> bool:
        """执行 unregister 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。

        Returns:
            bool，函数执行后的结果。
        """
        async with self._lock:
            removed = False
            if name in self._classes:
                del self._classes[name]
                removed = True
            if name in self._instances:
                del self._instances[name]
                removed = True
            if name in self._metadata:
                del self._metadata[name]
            if removed:
                logger.info("Unregistered agent: %s", name)
            return removed

    def list_agents(self) -> list[str]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Returns:
            list[str]，函数执行后的结果。
        """
        return sorted(set(self._classes.keys()) | set(self._instances.keys()))

    def get_agent_info(self, name: str) -> Optional[dict]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            name: str，调用方传入的 name 参数。

        Returns:
            Optional[dict]，函数执行后的结果。
        """
        if name not in self._metadata and name not in self._classes:
            return None
        info = dict(self._metadata.get(name, {}))
        if name in self._instances:
            info["status"] = self._instances[name].stats
        elif name in self._classes:
            info["status"] = "class_registered"
            info["class"] = self._classes[name].__name__
        return info

    async def get_all_stats(self) -> dict[str, dict]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            dict[str, dict]，函数执行后的结果。
        """
        stats = {}
        for name, agent in self._instances.items():
            stats[name] = agent.stats
        return stats

    async def reset_all(self) -> None:
        """执行 reset_all 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        for agent in self._instances.values():
            agent.reset()
        logger.info("Reset all %d agents to IDLE", len(self._instances))

    @property
    def count(self) -> int:
        """执行 count 对应的逻辑，并返回处理结果。

        Returns:
            int，函数执行后的结果。
        """
        return len(set(self._classes.keys()) | set(self._instances.keys()))
