"""智能体模块。"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.api.middleware.error_handler import NOT_FOUND
from agentforge.workflow.registry import AgentRegistry

logger = logging.getLogger(__name__)


class AgentRoutes:
    """智能体路由相关组件。"""

    def __init__(self, registry: AgentRegistry) -> None:
        """初始化 AgentRoutes。

        Args:
            registry: 注册表实例。
        """
        self.registry = registry

    async def list_agents(self) -> dict[str, Any]:
        """查询智能体。

        Returns:
            结构化结果字典。
        """
        agents = self.registry.list_agents()
        return {
            "agents": agents,
            "total": len(agents),
        }

    async def get_agent(self, name: str) -> dict[str, Any]:
        """读取智能体。

        Args:
            name: 资源或对象名称。

        Returns:
            结构化结果字典。

        Raises:
            NOT_FOUND: 操作无法完成时抛出。
        """
        if not self.registry.has(name):
            raise NOT_FOUND

        agent = self.registry.get(name)
        agent_info: dict[str, Any] = {
            "name": name,
            "type": type(agent).__name__,
            "module": type(agent).__module__,
        }

        # 如果 Agent 有工具注册表，列出工具
        if hasattr(agent, "tool_registry"):
            tool_names = agent.tool_registry.list_tool_names()
            agent_info["tools"] = tool_names

        # 如果 Agent 有 prompt_template
        if hasattr(agent, "prompt_template"):
            agent_info["has_prompt"] = bool(agent.prompt_template)

        return agent_info

    async def health_check(self) -> dict[str, Any]:
        """检查组件健康状态并返回诊断结果。

        Returns:
            结构化结果字典。
        """
        agents = self.registry.list_names()
        healthy: list[str] = []
        unhealthy: list[dict[str, str]] = []

        for name in agents:
            agent = self.registry.get(name)
            if hasattr(agent, "health_check"):
                try:
                    is_healthy = await agent.health_check()
                    if is_healthy:
                        healthy.append(name)
                    else:
                        unhealthy.append({"name": name, "reason": "unhealthy"})
                except Exception as e:
                    unhealthy.append({"name": name, "reason": str(e)})
            else:
                # 没有 health_check 方法的 Agent 默认健康
                healthy.append(name)

        return {
            "status": "healthy" if not unhealthy else "degraded",
            "total": len(agents),
            "healthy": healthy,
            "unhealthy": unhealthy,
        }
