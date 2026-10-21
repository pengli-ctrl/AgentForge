"""文档生成器智能体模块。"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.agent import Agent
from agentforge.core.base_tool import ToolRegistry

logger = logging.getLogger(__name__)


class DocGeneratorAgent(Agent):
    """文档生成智能体，根据代码和上下文生成项目文档。"""

    REQUIRED_CONTEXT_KEYS = ["code_review_result", "test_result"]

    def __init__(
        self,
        llm_gateway: Any,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        """初始化 DocGeneratorAgent。

        Args:
            llm_gateway: LLM 网关实例。
            tool_registry: 工具注册表。
        """
        super().__init__(
            llm_gateway=llm_gateway,
            name="doc-generator",
            tool_registry=tool_registry or ToolRegistry(),
            max_iterations=3,
            token_budget=4000,
        )

        self.prompt_template = (
            "你是一个文档生成助手。请基于以下信息生成变更文档。\n\n"
            "## 任务\n{task}\n\n"
            "## 上下文（审查结果和测试结果）\n{context}\n\n"
            "## 输出要求\n"
            "1. 生成 Markdown 格式的变更文档\n"
            "2. 包含变更摘要、详细变更列表、影响分析\n"
            "3. 标注 breaking changes\n"
        )

    def _extract_context(self, context_snapshot: dict[str, Any]) -> dict[str, Any]:
        """从上下文快照中提取文档生成需要的上下文。

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
            "doc_result": {
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
            {"role": "system", "content": "You are a documentation generator."},
            {"role": "user", "content": task},
        ]
