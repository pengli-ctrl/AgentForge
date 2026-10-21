"""LLM路由模块。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from agentforge.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """\
You are an intelligent workflow router for a multi-agent code review system.

Your task is to decide which agent should handle the task next, based on \
the current task, completed agent outputs, and available agents.

## Current Task
{task}

## Completed Agent Outputs
{agent_outputs}

## Available Next Agents
{available_agents}

## Instructions
Analyze the completed agent outputs and the current task to determine which \
agent should run next.

Consider:
1. What work has already been done (from completed outputs)?
2. What work still needs to be done (based on the task)?
3. Which available agent is best suited for the remaining work?

Respond with ONLY a JSON object (no markdown, no explanation):
{{"agent_name": "<name of the chosen agent>", \
"reason": "<brief explanation of why this agent should run next>"}}"""


@dataclass
class RouteDecision:
    """路由决策结果。

    Attributes:
        agent_name: 智能体名称。
        reason: 变更原因。
    """

    agent_name: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        """转换为字典格式。

        Returns:
            结构化结果字典。
        """
        return {"agent_name": self.agent_name, "reason": self.reason}


class LLMRouter:
    """LLM 驱动的工作流路由器。"""

    def __init__(
        self,
        llm_gateway: LLMGateway,
        default_agent: str = "code-review",
    ) -> None:
        """初始化 LLMRouter。

        Args:
            llm_gateway: LLM 网关实例。
            default_agent: 默认智能体。
        """
        self.llm_gateway = llm_gateway
        self.default_agent = default_agent

    async def route(
        self,
        task: str,
        agent_outputs: dict[str, Any],
        available_agents: list[str],
    ) -> dict[str, str]:
        """选择并返回模型路由。

        Args:
            task: 任务对象。
            agent_outputs: 智能体。
            available_agents: 可用智能体。

        Returns:
            结构化结果字典。
        """
        if not available_agents:
            logger.warning("No available agents for routing, using default")
            return {"agent_name": self.default_agent, "reason": "no agents available"}

        # 如果只有一个可选 Agent，直接返回
        if len(available_agents) == 1:
            agent = available_agents[0]
            logger.info("Only one agent available, auto-routing to %s", agent)
            return {"agent_name": agent, "reason": "only available agent"}

        # 构造 prompt
        prompt = self._build_prompt(task, agent_outputs, available_agents)

        # 调用 LLM
        messages = [
            {
                "role": "system",
                "content": "You are an intelligent workflow routing assistant.",
            },
            {"role": "user", "content": prompt},
        ]

        logger.info(
            "LLM routing started (task='%s', completed=%s, available=%s)",
            task[:80],
            list(agent_outputs.keys()),
            available_agents,
        )

        response = await self.llm_gateway.chat(
            messages,
            temperature=0.0,
        )

        # 解析 LLM 返回的 JSON
        decision = self._parse_route(response.content, available_agents)

        logger.info(
            "LLM routing decided (agent=%s, reason=%s)",
            decision.agent_name,
            decision.reason[:100],
        )

        return decision.to_dict()

    def _build_prompt(
        self,
        task: str,
        agent_outputs: dict[str, Any],
        available_agents: list[str],
    ) -> str:
        """构建提示词。

        Args:
            task: 任务对象。
            agent_outputs: 智能体。
            available_agents: 可用智能体。

        Returns:
            字符串结果。
        """
        # 格式化已完成 Agent 的输出
        if agent_outputs:
            output_lines: list[str] = []
            for agent_name, output in agent_outputs.items():
                output_str = (
                    json.dumps(output, ensure_ascii=False, default=str)
                    if isinstance(output, (dict, list))
                    else str(output)
                )
                # 截断过长的输出
                if len(output_str) > 500:
                    output_str = output_str[:500] + "..."
                output_lines.append(f"  - {agent_name}: {output_str}")
            outputs_text = "\n".join(output_lines)
        else:
            outputs_text = "  (no agents have completed yet)"

        # 格式化可选 Agent 列表
        agents_text = "\n".join(f"  - {a}" for a in available_agents)

        return ROUTER_PROMPT.format(
            task=task,
            agent_outputs=outputs_text,
            available_agents=agents_text,
        )

    def _parse_route(
        self,
        llm_output: str,
        available_agents: list[str],
    ) -> RouteDecision:
        """解析路由。

        Args:
            llm_output: LLM输出。
            available_agents: 可用智能体。

        Returns:
            路由决策结果。
        """
        json_str = self._extract_json(llm_output)

        if json_str is None:
            logger.warning(
                "Failed to parse LLM route output, using default: %s",
                self.default_agent,
            )
            return RouteDecision(
                agent_name=self.default_agent,
                reason="parse_error: invalid JSON from LLM",
            )

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(
                "LLM route JSON decode failed, using default: %s",
                self.default_agent,
            )
            return RouteDecision(
                agent_name=self.default_agent,
                reason="parse_error: JSON decode failed",
            )

        agent_name = str(data.get("agent_name", "")).strip()
        reason = str(data.get("reason", "")).strip()

        # 验证 agent_name 是否在可用列表中
        if agent_name not in available_agents:
            logger.warning(
                "LLM selected agent '%s' not in available list %s, " "using default: %s",
                agent_name,
                available_agents,
                self.default_agent,
            )
            return RouteDecision(
                agent_name=self.default_agent,
                reason=f"invalid_agent: LLM chose '{agent_name}' "
                f"which is not in available list",
            )

        return RouteDecision(agent_name=agent_name, reason=reason)

    def _extract_json(self, text: str) -> str | None:
        """提取JSON。

        Args:
            text: 待处理文本。

        Returns:
            无结果。
        """
        text = text.strip()

        # 尝试直接解析
        if text.startswith("{"):
            return text

        # 尝试从 markdown 代码块中提取
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{") and part.rstrip().endswith("}"):
                    return part.rstrip()

        # 尝试找到第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]

        return None
