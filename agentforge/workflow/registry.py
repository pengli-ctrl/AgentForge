"""注册表模块。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentRegistry:
    """智能体注册表。"""

    def __init__(self) -> None:
        """初始化 AgentRegistry。"""
        self._agents: dict[str, Any] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        agent: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """注册智能体。

        Args:
            name: 资源或对象名称。
            agent: 智能体。
            metadata: 附加元数据。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if name in self._agents:
            raise ValueError(f"Agent '{name}' is already registered")

        self._agents[name] = agent
        self._metadata[name] = metadata or {}

        logger.info(
            "Agent registered (name=%s, metadata=%s)",
            name,
            self._metadata[name],
        )

    def register_many(self, agents: dict[str, Any]) -> None:
        """注册智能体。

        Args:
            agents: 智能体。
        """
        for name, agent in agents.items():
            if name not in self._agents:
                self.register(name, agent)

    def unregister(self, name: str) -> Any | None:
        """注销智能体。

        Args:
            name: 资源或对象名称。

        Returns:
            无结果。
        """
        agent = self._agents.pop(name, None)
        self._metadata.pop(name, None)

        if agent:
            logger.info("Agent unregistered (name=%s)", name)

        return agent

    def get(self, name: str) -> Any | None:
        """读取智能体。

        Args:
            name: 资源或对象名称。

        Returns:
            无结果。
        """
        return self._agents.get(name)

    def has(self, name: str) -> bool:
        """判断指定键或名称是否存在。

        Args:
            name: 资源或对象名称。

        Returns:
            操作是否成功。
        """
        return name in self._agents

    def list_agents(self) -> list[dict[str, Any]]:
        """查询智能体。

        Returns:
            结果列表。
        """
        return [{"name": name, "metadata": self._metadata[name]} for name in self._agents]

    def list_names(self) -> list[str]:
        """查询名称。

        Returns:
            结果列表。
        """
        return list(self._agents.keys())

    def clear(self) -> None:
        """清空注册表。"""
        count = len(self._agents)
        self._agents.clear()
        self._metadata.clear()
        logger.info("Agent registry cleared (%d agents removed)", count)
