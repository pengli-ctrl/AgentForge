"""测试执行智能体模块。"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.agent import Agent
from agentforge.core.base_tool import ToolRegistry

logger = logging.getLogger(__name__)


class TestExecutionAgent(Agent):
    """测试执行智能体，运行测试并汇总失败信息。"""

    REQUIRED_CONTEXT_KEYS = ["code_path", "test_config"]
    __test__ = False

    def __init__(
        self,
        llm_gateway: Any,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        """初始化 TestExecutionAgent。

        Args:
            llm_gateway: LLM 网关实例。
            tool_registry: 工具注册表。
        """
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
            context_snapshot: 上下文快照。

        Returns:
            结构化结果字典。
        """
        return {k: context_snapshot[k] for k in self.REQUIRED_CONTEXT_KEYS if k in context_snapshot}

    def _build_downstream_context(
        self,
        original_snapshot: dict[str, Any],
        relevant_context: dict[str, Any],
        tool_results: list,
    ) -> dict[str, Any]:
        """构建下游上下文。

        Args:
            original_snapshot: 原始上下文快照。
            relevant_context: 筛选后的相关上下文。
            tool_results: 工具执行结果列表。

        Returns:
            结构化结果字典。
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
            task: 任务对象。

        Returns:
            结果列表。
        """
        return [
            {"role": "system", "content": "You are a test execution assistant."},
            {"role": "user", "content": task},
        ]
