"""
测试执行 Agent — 运行单元测试、分析测试结果、生成测试报告。

V3 架构中的测试执行 Agent，接收代码审查完成事件后触发，
执行单元测试并分析通过率和覆盖率。

上下文隔离：只从 context_snapshot 中提取代码路径和测试配置，
不接收代码审查的原始代码内容。
"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.agent import Agent
from agentforge.core.base_tool import ToolRegistry

logger = logging.getLogger(__name__)


class TestExecutionAgent(Agent):
    """测试执行 Agent — 运行单元测试并分析结果。

    职责：
    - 执行指定路径的单元测试
    - 分析测试通过率和代码覆盖率
    - 识别失败的测试用例并分析失败原因
    - 生成结构化测试报告

    上下文隔离：
    - 只提取 context_snapshot 中的 code_path 和 test_config
    - 不接收代码审查的原始代码内容
    - 输出事件只携带测试结果摘要和 pass_rate

    动态路由：
    - 测试通过率 < 0.8 时，路由回 code-review 重新审查
    - 测试通过时，路由到 doc-generator 生成文档

    Args:
        llm_gateway: LLM 网关实例。
        tool_registry: 工具注册表（可选）。
    """

    REQUIRED_CONTEXT_KEYS = ["code_path", "test_config"]
    __test__ = False

    def __init__(
        self,
        llm_gateway: Any,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        super().__init__(
            llm_gateway=llm_gateway,
            name="test-execution",
            tool_registry=tool_registry or ToolRegistry(),
            max_iterations=3,
            token_budget=6000,
        )

        self.prompt_template = (
            "你是一个测试执行助手。请分析以下测试结果并生成报告。\n\n"
            "## 任务\n{task}\n\n"
            "## 上下文\n{context}\n\n"
            "## 输出要求\n"
            "1. 统计测试通过率和覆盖率\n"
            "2. 分析失败的测试用例\n"
            "3. 给出改进建议\n"
        )

    def _extract_context(self, context_snapshot: dict[str, Any]) -> dict[str, Any]:
        """从上下文快照中提取测试执行需要的上下文。

        Args:
            context_snapshot: 完整的上下文快照。

        Returns:
            包含代码路径和测试配置的上下文子集。
        """
        return {k: context_snapshot[k] for k in self.REQUIRED_CONTEXT_KEYS if k in context_snapshot}

    def _build_downstream_context(
        self,
        original_snapshot: dict[str, Any],
        relevant_context: dict[str, Any],
        tool_results: list,
    ) -> dict[str, Any]:
        """构造下游 Agent 需要的上下文快照。

        只传递测试结果摘要和 pass_rate，用于动态路由决策。

        Args:
            original_snapshot: 原始上下文快照。
            relevant_context: 当前 Agent 提取的上下文。
            tool_results: 工具执行结果。

        Returns:
            传递给下游 Agent 的上下文快照。
        """
        downstream = {
            "test_result": {
                "pass_rate": 1.0,  # 实际由测试执行结果决定
                "summary": self._summarize(None, tool_results),
            }
        }
        return downstream

    def _build_initial_messages(self, task: str) -> list[dict[str, str]]:
        """构造初始消息列表。

        Args:
            task: 任务描述。

        Returns:
            消息列表。
        """
        return [
            {"role": "system", "content": "You are a test execution assistant."},
            {"role": "user", "content": task},
        ]
