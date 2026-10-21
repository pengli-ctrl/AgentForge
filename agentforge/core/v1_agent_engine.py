"""智能体引擎模块。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolRegistry
from agentforge.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """智能体结果领域组件。

    Attributes:
        output: 输出。
        iterations: 迭代次数。
        tool_calls: 工具调用。
        token_usage: 令牌用量。
    """

    output: str
    iterations: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    token_usage: int = 0


class AgentEngine:
    """智能体领域组件。"""

    def __init__(
        self,
        llm_gateway: LLMGateway,
        max_iterations: int = 5,
    ):
        """初始化 AgentEngine。

        Args:
            llm_gateway: LLM 网关实例。
            max_iterations: 最大迭代次数。
        """
        self.llm = llm_gateway
        self.tool_registry = ToolRegistry()  # 统一工具注册表
        self.max_iterations = max_iterations  # 防止无限循环
        self.token_budget = 8000  # Prompt token 预算

    def register_tool(self, tool: BaseTool) -> None:
        """注册工具到统一工具注册表。

        Args:
            tool: 工具。
        """
        self.tool_registry.register(tool)
        logger.info(f"Tool registered: {tool.name}")

    async def execute(self, task: str) -> AgentResult:
        """执行核心处理逻辑并返回结果。

        Args:
            task: 任务对象。

        Returns:
            智能体结果结果。
        """
        messages = self._build_initial_messages(task)
        tool_calls_history: list[dict[str, Any]] = []
        total_tokens = 0

        for i in range(self.max_iterations):
            response = await self.llm.chat(
                messages=messages,
                tools=self.tool_registry.get_schemas(),
                max_tokens=self.token_budget,
            )
            total_tokens += response.usage.get(
                "total_tokens",
                response.usage.get("prompt_tokens", 0) + response.usage.get("completion_tokens", 0),
            )

            if response.has_tool_calls:
                for call in response.tool_calls:
                    result = await self.tool_registry.execute(call.name, call.arguments)
                    messages.append({"role": "tool", "content": result.to_json()})
                    tool_calls_history.append(
                        {
                            "tool": call.name,
                            "arguments": call.arguments,
                            "success": result.success,
                        }
                    )
            else:
                return AgentResult(
                    output=response.content,
                    iterations=i + 1,
                    tool_calls=tool_calls_history,
                    token_usage=total_tokens,
                )

        logger.warning(f"Agent reached max iterations ({self.max_iterations})")
        return AgentResult(
            output="[max iterations reached]",
            iterations=self.max_iterations,
            tool_calls=tool_calls_history,
            token_usage=total_tokens,
        )

    def _build_initial_messages(self, task: str) -> list[dict[str, str]]:
        """构造初始消息列表。

        Args:
            task: 任务对象。

        Returns:
            结果列表。
        """
        return [
            {
                "role": "system",
                "content": (
                    "你是一个代码审查 Agent。根据用户提交的代码，"
                    "分析代码质量、安全风险和最佳实践 violations，"
                    "给出具体的修改建议。"
                    "你可以调用以下工具来辅助分析："
                    f"{self.tool_registry.get_tool_descriptions()}"
                ),
            },
            {"role": "user", "content": task},
        ]
