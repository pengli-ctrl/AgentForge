"""Agent 管理 REST 接口 — Agent 注册、状态查询、健康检查。

API 端点：
    GET    /api/v1/agents          — 查询 Agent 列表
    GET    /api/v1/agents/{name}   — 查询 Agent 详情
    POST   /api/v1/agents/{name}/register — 注册 Agent
    GET    /api/v1/agents/health   — 健康检查
"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.api.middleware.error_handler import NOT_FOUND, VALIDATION_ERROR
from agentforge.workflow.registry import AgentRegistry

logger = logging.getLogger(__name__)


class AgentRoutes:
    """Agent 管理路由处理器。

    封装 Agent 相关的 HTTP 请求处理逻辑。

    Args:
        registry: Agent 注册表。
    """

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    async def list_agents(self) -> dict[str, Any]:
        """查询所有已注册的 Agent。

        Returns:
            Agent 列表信息。
        """
        agents = self.registry.list_agents()
        return {
            "agents": agents,
            "total": len(agents),
        }

    async def get_agent(self, name: str) -> dict[str, Any]:
        """查询单个 Agent 详情。

        Args:
            name: Agent 名称。

        Returns:
            Agent 信息。

        Raises:
            APIError: Agent 不存在时抛出 NOT_FOUND。
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

    async def register_agent(self, name: str, body: dict[str, Any]) -> dict[str, Any]:
        """注册 Agent（通过工厂模式）。

        Args:
            name: Agent 名称。
            body: 请求体，包含 agent_type 和 config。

        Returns:
            注册结果。

        Raises:
            APIError: 参数缺失时抛出 VALIDATION_ERROR。
        """
        agent_type = body.get("agent_type", "")
        if not agent_type:
            raise VALIDATION_ERROR

        # 实际注册逻辑需要根据 agent_type 创建对应实例
        # 这里返回注册信息，实际注册由调用方完成
        logger.info(
            "Agent registration requested (name=%s, type=%s)",
            name,
            agent_type,
        )

        return {
            "name": name,
            "agent_type": agent_type,
            "status": "registered",
        }

    async def health_check(self) -> dict[str, Any]:
        """Agent 健康检查。

        检查所有已注册 Agent 的健康状态。

        Returns:
            健康检查结果。
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
