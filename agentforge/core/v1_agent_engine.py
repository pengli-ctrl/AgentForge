"""
V1 单 Agent 引擎 — ReAct 循环（思考 → 行动 → 观察 → 再思考）。

这是 AgentForge 的起点：一个结构清晰的单 Agent，用最短时间验证
"Agent + LLM + 工具调用" 这条技术路线是否可行。

V1 的设计原则：
- 只验证核心假设：LLM 能否可靠地驱动工具调用完成代码审查任务？
- 刻意不做的事：多 Agent 编排、复杂状态管理、可视化界面
- 刻意要做的事：基础的工具抽象层、异步执行、错误重试、简单的可观测性

PoC 验证结果（3 周上线）：
- 工具调用成功率 94%
- 代码审查建议采纳率 67%
- 团队日活稳定 200+

天花板：
- 3 个以上工具调用后 Prompt 超 32K tokens，幻觉率飙升
- 代码分析、测试、文档串行执行，单次任务 3-5 分钟
- 无法拆分新 Agent，工具调用逻辑全耦合在一起

→ V2 解决了 Agent 拆分问题，但引入了共享状态耦合
→ V3 用事件总线 + Context Snapshot 彻底解决

此文件保留用于架构演进参考，生产环境请使用 V3 的 Agent 基类。
详见 agentforge.core.agent。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolRegistry
from agentforge.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Agent 执行结果。

    Attributes:
        output: 最终输出内容
        iterations: 实际执行的 ReAct 迭代次数
        tool_calls: 工具调用历史记录
        token_usage: 总 token 消耗
    """

    output: str
    iterations: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    token_usage: int = 0


class AgentEngine:
    """V1 单 Agent 引擎 — ReAct 循环。

    核心流程：思考 → 行动 → 观察 → 再思考...直到得出最终答案或达到最大迭代次数。

    V1 最值得设计的部分是 BaseTool 统一接口——即使是最简单的 PoC，
    工具调用也不能直接写在业务代码里。这个接口后来直接被 V2/V3 继承，
    省了大量重构成本。

    Args:
        llm_gateway: LLM 推理网关（vLLM 私有化部署）
        max_iterations: 最大 ReAct 迭代次数，防止无限循环
        token_budget: 单次 LLM 调用的 token 预算

    Example:
        >>> engine = AgentEngine(llm_gateway=gateway, max_iterations=5)
        >>> result = await engine.execute("审查 src/auth/login.py 的代码质量")
        >>> print(result.output)
    """

    def __init__(
        self,
        llm_gateway: LLMGateway,
        max_iterations: int = 5,
    ):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            llm_gateway: LLMGateway，调用方传入的 llm_gateway 参数。
            max_iterations: int，调用方传入的 max_iterations 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.llm = llm_gateway
        self.tool_registry = ToolRegistry()  # 统一工具注册表
        self.max_iterations = max_iterations  # 防止无限循环
        self.token_budget = 8000  # Prompt token 预算

    def register_tool(self, tool: BaseTool) -> None:
        """注册工具到统一工具注册表。"""
        self.tool_registry.register(tool)
        logger.info(f"Tool registered: {tool.name}")

    async def execute(self, task: str) -> AgentResult:
        """执行 ReAct 循环：思考 → 行动 → 观察 → 再思考。

        Args:
            task: 用户任务描述

        Returns:
            AgentResult: 包含最终输出、迭代次数和工具调用历史
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

        包含 system prompt（角色定义 + 工具使用说明）和 user message（任务描述）。
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
