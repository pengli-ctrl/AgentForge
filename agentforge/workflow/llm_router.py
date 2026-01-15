"""
LLM 路由器 — 用 LLM 替代 YAML 中的 if-else 路由决策。

博客 05「渐进式引入策略」的第一步：在 YAML 硬编码路由的基础上，
引入 LLM 做更灵活的路由决策。

设计原则（博客强调）：
1. LLM 只负责"选哪个 Agent" — 下游节点的执行逻辑仍是确定性代码
2. LLM 返回 JSON 格式的路由决策，用确定性代码解析和执行
3. 如果 LLM 返回了不存在的 Agent 名称，降级为 default 路由
4. 路由决策可追溯 — 每次决策都记录 reason 字段

典型场景：
- CodeReview Agent 输出 "critical" → YAML 路由到 SecurityScan
- 但如果输出是 "complexity high, no security issue" → YAML 不知道怎么路由
- LLM Router 可以理解这种自然语言输出，选择最合适的下一个 Agent

引入路径（渐进式）：
1. 先在 default 分支用 LLM Router（最安全，只处理 YAML 处理不了的情况）
2. 验证效果后逐步替换更多条件分支
3. 最终大部分路由由 LLM 决策，YAML 只保留兜底逻辑
"""

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
        agent_name: 被选中的 Agent 名称。
        reason: LLM 给出的路由理由。
    """

    agent_name: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        """转换为字典格式。"""
        return {"agent_name": self.agent_name, "reason": self.reason}


class LLMRouter:
    """LLM 驱动的工作流路由器。

    用 LLM 替代 YAML 中的 if-else 条件路由。LLM 理解 Agent 输出的语义，
    选择最合适的下一个 Agent。

    设计原则：
    - LLM 只做"选哪个 Agent"的决策，不做执行
    - 下游节点执行逻辑仍是确定性代码（不依赖 LLM）
    - LLM 返回 JSON，用确定性代码解析
    - 如果 LLM 选了不存在的 Agent，降级为 default_agent

    Args:
        llm_gateway: LLM 网关实例。
        default_agent: LLM 路由失败时的兜底 Agent 名称。
    """

    def __init__(
        self,
        llm_gateway: LLMGateway,
        default_agent: str = "code-review",
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            llm_gateway: LLMGateway，调用方传入的 llm_gateway 参数。
            default_agent: str，调用方传入的 default_agent 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.llm_gateway = llm_gateway
        self.default_agent = default_agent

    async def route(
        self,
        task: str,
        agent_outputs: dict[str, Any],
        available_agents: list[str],
    ) -> dict[str, str]:
        """用 LLM 决定下一个执行哪个 Agent。

        流程：
        1. 构造 prompt：包含当前任务、已完成 Agent 输出、可选 Agent
        2. 调用 LLM 获取路由决策 JSON
        3. 解析 JSON，提取 agent_name 和 reason
        4. 验证 agent_name 是否在 available_agents 中
        5. 如果无效，降级为 default_agent

        Args:
            task: 当前任务描述。
            agent_outputs: 已完成 Agent 的输出字典 {agent_name: output}。
            available_agents: 可选的下一个 Agent 名称列表。

        Returns:
            路由决策字典 ``{"agent_name": "...", "reason": "..."}``。
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
        """构造路由 prompt。

        Args:
            task: 当前任务描述。
            agent_outputs: 已完成 Agent 的输出。
            available_agents: 可选 Agent 列表。

        Returns:
            格式化后的 prompt 字符串。
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
        """解析 LLM 返回的路由决策 JSON。

        期望格式：
            {"agent_name": "security-scan", "reason": "..."}

        解析失败或 agent_name 无效时降级为 default_agent。

        Args:
            llm_output: LLM 返回的文本。
            available_agents: 合法的 Agent 名称列表。

        Returns:
            RouteDecision 对象。
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
        """从 LLM 输出中提取 JSON 字符串。

        处理 LLM 可能添加的 markdown 代码块标记。

        Args:
            text: LLM 输出文本。

        Returns:
            提取的 JSON 字符串，失败返回 None。
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
