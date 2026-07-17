"""
Agent 基类 — V3 事件驱动架构中的 Agent 执行环境。

每个 Agent 是一个独立的事件处理单元，状态完全隔离。Agent 只从
context_snapshot 中提取自己需要的上下文，不接收全量数据，
解决了 V2 中 context 字典无限膨胀和 Prompt 爆炸的问题。

核心执行流程（execute 方法）— ReAct 循环：
1. 从快照中提取自己需要的上下文（状态隔离的核心）
2. 用局部状态 + 事件上下文构造 Prompt（Prompt 不再爆炸）
3. ReAct 循环：思考 → 行动 → 观察 → 再思考
   - 调用 LLM，检查是否有 tool_calls
   - 有 tool_calls → 执行工具 → 将结果作为 observation 加入 messages → 继续循环
   - 无 tool_calls → 得出最终答案，终止循环
4. 构造输出事件 — 只传递下游 Agent 需要的上下文

ReAct 循环是 Agent 的核心推理模式：
- 每次迭代 LLM 可以选择调用工具获取更多信息
- 工具执行结果作为 observation 反馈给 LLM
- LLM 基于观察结果继续推理，直到得出最终答案
- 终止条件：LLM 返回无 tool_calls、达到 max_iterations、或 token 预算耗尽
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agentforge.core.base_tool import ToolRegistry, ToolResult
from agentforge.core.event_types import AgentEvent, EventType

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Agent 执行结果。

    Attributes:
        output: Agent 输出内容。
        iterations: ReAct 循环迭代次数。
        tool_results: 工具执行结果列表。
        success: 执行是否成功。
    """

    output: str = ""
    iterations: int = 0
    tool_results: list[ToolResult] = field(default_factory=list)
    success: bool = True


class Agent(ABC):
    """Agent 基类 — 事件驱动架构中的独立执行单元。

    每个 Agent 有独立的 Prompt 模板和工具集，通过事件总线与其他 Agent 通信。
    Agent 不认识其他 Agent，只认识事件 — 这是事件驱动的核心价值。

    状态隔离设计：
    - 每个 Agent 只从 context_snapshot 中提取自己需要的上下文
    - 发送方决定下游能看什么（_build_downstream_context）
    - Agent 间不共享可变状态

    ReAct 循环：
    - Agent 通过 ReAct（Reasoning + Acting）模式进行多轮推理
    - 每轮可以调用工具获取信息，工具结果作为观察反馈给 LLM
    - 循环终止条件：LLM 返回无 tool_calls、达到 max_iterations、token 预算耗尽

    Args:
        llm_gateway: LLM 网关实例。
        name: Agent 名称。
        tool_registry: 工具注册表（可选）。
        max_iterations: ReAct 循环最大迭代次数。
        token_budget: Prompt token 预算。

    Attributes:
        prompt_template: Agent 的 Prompt 模板（子类设置）。
    """

    def __init__(
        self,
        llm_gateway: Any,
        name: str,
        tool_registry: ToolRegistry | None = None,
        max_iterations: int = 5,
        token_budget: int = 8000,
    ) -> None:
        self.llm_gateway = llm_gateway
        self.name = name
        self.tool_registry = tool_registry or ToolRegistry()
        self.max_iterations = max_iterations
        self.token_budget = token_budget
        self.prompt_template: str = ""

    async def execute(self, event: AgentEvent) -> AgentEvent:
        """处理事件并返回输出事件 — V3 事件驱动的核心执行方法。

        执行 ReAct 循环：
        1. 从快照中提取自己需要的上下文（状态隔离的核心）
        2. 用局部状态 + 事件上下文构造 Prompt
        3. ReAct 循环：思考 → 行动 → 观察 → 再思考
        4. 构造输出事件 — 只传递下游 Agent 需要的上下文

        Args:
            event: 接收到的 Agent 事件，包含 context_snapshot 和 payload。

        Returns:
            输出事件，携带结果和下游需要的上下文快照。
        """
        # 1. 只从快照中提取自己需要的上下文（状态隔离的核心）
        relevant_context = self._extract_context(event.context_snapshot)

        # 2. 用局部状态 + 事件上下文构造 Prompt（Prompt 不再爆炸）
        task_desc = event.payload.get("task", "")
        if self.prompt_template:
            prompt = self.prompt_template.format(
                task=task_desc,
                context=relevant_context,
            )
        else:
            prompt = task_desc

        # 3. 构造初始消息列表（子类实现）
        messages = self._build_initial_messages(prompt)

        # 获取工具 Schema（如果有注册工具）
        tools = self.tool_registry.get_schemas() or None

        # 4. ReAct 循环：思考 → 行动 → 观察 → 再思考
        all_tool_results: list[ToolResult] = []
        accumulated_tokens = 0
        response: Any = None
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1

            # Token 预算检查 — 接近预算时强制终止
            if accumulated_tokens >= self.token_budget:
                logger.warning(
                    "Token budget exceeded, forcing ReAct termination "
                    "(agent=%s, tokens=%d/%d, iteration=%d)",
                    self.name,
                    accumulated_tokens,
                    self.token_budget,
                    iteration,
                )
                break

            # 调用 LLM 进行推理
            response = await self.llm_gateway.chat(messages, tools=tools)

            # 累计 token 使用量
            if response.usage:
                accumulated_tokens += response.usage.get("total_tokens", 0)

            logger.debug(
                "ReAct iteration %d (agent=%s, tool_calls=%d, tokens=%d/%d)",
                iteration,
                self.name,
                len(response.tool_calls) if response.has_tool_calls else 0,
                accumulated_tokens,
                self.token_budget,
            )

            # 终止条件：LLM 返回无 tool_calls → 得出最终答案
            if not response.has_tool_calls or not response.tool_calls:
                logger.info(
                    "ReAct loop completed (agent=%s, iterations=%d, " "final_answer_length=%d)",
                    self.name,
                    iteration,
                    len(response.content),
                )
                break

            # 执行工具调用
            tool_results = await self._execute_tools(response)
            all_tool_results.extend(tool_results)

            # 将 LLM 响应加入消息历史（assistant 角色）
            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                }
            )

            # 将工具执行结果作为 observation 加入消息历史
            for tr in tool_results:
                messages.append(
                    {
                        "role": "user",
                        "content": f"[Tool Observation] {tr.to_json()}",
                    }
                )

            logger.info(
                "ReAct iteration %d: %d tools executed (agent=%s)",
                iteration,
                len(tool_results),
                self.name,
            )

        # 如果循环结束但 response 仍为 None（max_iterations=0 的边界情况）
        if response is None:
            from agentforge.llm.gateway import LLMResponse

            response = LLMResponse(content="", model="")

        logger.info(
            "Agent execute completed (agent=%s, iterations=%d, " "tool_calls=%d, tokens=%d)",
            self.name,
            iteration,
            len(all_tool_results),
            accumulated_tokens,
        )

        # 5. 构造输出事件 — 只传递下游 Agent 需要的上下文
        return AgentEvent(
            event_type=EventType.AGENT_COMPLETED,
            source_agent=self.name,
            payload={"result": self._summarize(response, all_tool_results)},
            correlation_id=event.correlation_id,
            context_snapshot=self._build_downstream_context(
                event.context_snapshot, relevant_context, all_tool_results
            ),
        )

    def _extract_context(self, context_snapshot: dict[str, Any]) -> dict[str, Any]:
        """从上下文快照中提取当前 Agent 需要的上下文。

        子类实现此方法，只提取自己需要的数据，而不是接收全量数据。
        这是 V3 状态隔离的核心 — 解决了 V2 中 context 字典无限膨胀的问题。

        Args:
            context_snapshot: 完整的上下文快照。

        Returns:
            当前 Agent 需要的上下文子集。
        """
        return context_snapshot

    async def _execute_tools(self, response: Any) -> list[ToolResult]:
        """执行 LLM 响应中的工具调用。

        Args:
            response: LLM 响应对象。

        Returns:
            工具执行结果列表。
        """
        results: list[ToolResult] = []

        if not hasattr(response, "tool_calls") or not response.tool_calls:
            return results

        for call in response.tool_calls:
            result = await self.tool_registry.execute(call.name, call.arguments)
            results.append(result)
            logger.info(
                "Tool executed: %s (success=%s, agent=%s)",
                call.name,
                result.success,
                self.name,
            )

        return results

    def _build_downstream_context(
        self,
        original_snapshot: dict[str, Any],
        relevant_context: dict[str, Any],
        tool_results: list[ToolResult],
    ) -> dict[str, Any]:
        """构造下游 Agent 需要的上下文快照。

        发送方决定下游能看什么 — 只传递下游 Agent 需要的上下文，
        而不是全量数据。这是状态隔离设计的另一半。

        Args:
            original_snapshot: 原始上下文快照。
            relevant_context: 当前 Agent 提取的上下文。
            tool_results: 当前 Agent 的工具执行结果。

        Returns:
            传递给下游 Agent 的上下文快照。
        """
        downstream = dict(original_snapshot)
        downstream[f"{self.name}_result"] = {
            "output": self._summarize(None, tool_results),
        }
        return downstream

    def _summarize(self, response: Any, tool_results: list[ToolResult]) -> str:
        """汇总 LLM 响应和工具结果为简洁摘要。

        Args:
            response: LLM 响应对象。
            tool_results: 工具执行结果列表。

        Returns:
            结果摘要字符串。
        """
        parts: list[str] = []
        if response and hasattr(response, "content") and response.content:
            parts.append(response.content)
        for tr in tool_results:
            if tr.success:
                parts.append(tr.output)
        return "\n".join(parts) if parts else ""

    @abstractmethod
    def _build_initial_messages(self, task: str) -> list[dict[str, str]]:
        """构造初始消息列表（子类实现）。

        Args:
            task: 任务描述。

        Returns:
            消息列表，用于 LLM 调用。
        """
        ...
