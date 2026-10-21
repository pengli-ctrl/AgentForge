"""智能体注册表模块。"""

import logging
from typing import Optional, Type

from agentforge.core.agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """智能体注册表。"""

    def __init__(self):
        """初始化 AgentRegistry。"""
        self._classes: dict[str, Type[BaseAgent]] = {}
        self._instances: dict[str, BaseAgent] = {}
        self._metadata: dict[str, dict] = {}
        import asyncio

        self._lock = asyncio.Lock()

    async def register(
        self,
        name: str,
        agent_class: Type[BaseAgent],
        metadata: Optional[dict] = None,
    ) -> None:
        """注册智能体。

        Args:
            name: 资源或对象名称。
            agent_class: 智能体类。
            metadata: 附加元数据。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
            KeyError: 缺少必要配置或目标对象时抛出。
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
        """注册实例。

        Args:
            name: 资源或对象名称。
            agent: 智能体。
            metadata: 附加元数据。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
            KeyError: 缺少必要配置或目标对象时抛出。
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
        """读取智能体。

        Args:
            name: 资源或对象名称。

        Returns:
            基础智能体结果。

        Raises:
            KeyError: 缺少必要配置或目标对象时抛出。
        """
        async with self._lock:
            # 就绪状态。
            if name in self._instances:
                return self._instances[name]

            if name in self._classes:
                agent_class = self._classes[name]
                instance = agent_class(name=name)
                self._instances[name] = instance
                logger.info("Lazy-initialized agent: %s", name)
                return instance

            raise KeyError(f"Agent '{name}' is not registered")

    async def unregister(self, name: str) -> bool:
        """注销智能体。

        Args:
            name: 资源或对象名称。

        Returns:
            操作是否成功。
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
        """查询智能体。

        Returns:
            结果列表。
        """
        return sorted(set(self._classes.keys()) | set(self._instances.keys()))

    def get_agent_info(self, name: str) -> Optional[dict]:
        """读取智能体信息。

        Args:
            name: 资源或对象名称。

        Returns:
            处理结果对象。
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
        """获取全部统计。

        Returns:
            结构化结果字典。
        """
        stats = {}
        for name, agent in self._instances.items():
            stats[name] = agent.stats
        return stats

    async def reset_all(self) -> None:
        """重置全部注册状态。"""
        for agent in self._instances.values():
            agent.reset()
        logger.info("Reset all %d agents to IDLE", len(self._instances))

    @property
    def count(self) -> int:
        """统计智能体。

        Returns:
            整数结果。
        """
        return len(set(self._classes.keys()) | set(self._instances.keys()))
