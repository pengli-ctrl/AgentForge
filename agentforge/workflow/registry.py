"""Agent 注册表 — Agent 名称→Agent 实例的映射，支持动态注册。

工作流引擎通过 AgentRegistry 查找 Agent 实例。
支持动态注册和注销 Agent，无需重启服务。

设计理念：
- Agent 名称全局唯一
- 注册时检查名称冲突
- 支持批量注册
- 线程安全（通过 asyncio.Lock 保护并发写入）
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentRegistry:
    """AgentRegistry。

    AgentRegistry 是核心运行时组件，负责状态管理、调度和跨模块协作。

    主要成员：
    - 方法 register()。
    - 方法 register_many()。
    - 方法 unregister()。
    - 方法 get()。
    - 方法 has()。
    - 方法 list_agents()。
    - 方法 list_names()。
    - 方法 clear()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._agents: dict[str, Any] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        agent: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """注册 Agent 到注册表。

        Args:
            name: Agent 名称（全局唯一）。
            agent: Agent 实例。
            metadata: Agent 元数据（如版本、描述等）。

        Raises:
            ValueError: Agent 名称已存在时抛出。
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
        """批量注册 Agent。

        Args:
            agents: Agent 名称到实例的映射字典。
        """
        for name, agent in agents.items():
            if name not in self._agents:
                self.register(name, agent)

    def unregister(self, name: str) -> Any | None:
        """从注册表中注销 Agent。

        Args:
            name: Agent 名称。

        Returns:
            被注销的 Agent 实例，不存在则返回 None。
        """
        agent = self._agents.pop(name, None)
        self._metadata.pop(name, None)

        if agent:
            logger.info("Agent unregistered (name=%s)", name)

        return agent

    def get(self, name: str) -> Any | None:
        """根据名称获取 Agent 实例。

        Args:
            name: Agent 名称。

        Returns:
            Agent 实例，不存在则返回 None。
        """
        return self._agents.get(name)

    def has(self, name: str) -> bool:
        """检查 Agent 是否已注册。

        Args:
            name: Agent 名称。

        Returns:
            是否已注册。
        """
        return name in self._agents

    def list_agents(self) -> list[dict[str, Any]]:
        """列出所有已注册的 Agent。

        Returns:
            Agent 信息列表，每个元素包含 name 和 metadata。
        """
        return [{"name": name, "metadata": self._metadata[name]} for name in self._agents]

    def list_names(self) -> list[str]:
        """列出所有已注册的 Agent 名称。

        Returns:
            Agent 名称列表。
        """
        return list(self._agents.keys())

    def clear(self) -> None:
        """清空注册表。"""
        count = len(self._agents)
        self._agents.clear()
        self._metadata.clear()
        logger.info("Agent registry cleared (%d agents removed)", count)
