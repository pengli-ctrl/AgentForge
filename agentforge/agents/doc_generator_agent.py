"""
文档生成 Agent — 基于代码变更和审查结果生成变更文档。

V3 架构中的文档生成 Agent，是最独立的 Agent — 只接收输入、产出文档，
不和其他 Agent 交互。在 V2→V3 灰度迁移中，它是第一个被切到事件驱动模式的 Agent。
"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.agent import Agent
from agentforge.core.base_tool import ToolRegistry

logger = logging.getLogger(__name__)


class DocGeneratorAgent(Agent):
    """文档生成 Agent — 基于代码变更生成变更文档。

    职责：
    - 基于代码审查结果和测试报告生成变更文档
    - 生成 API 变更说明
    - 生成 changelog 条目
    - 标注 breaking changes

    上下文隔离：
    - 只提取 context_snapshot 中的 code_review_result 和 test_result
    - 不接收原始代码内容
    - 是最独立的 Agent，不和其他 Agent 形成反馈环

    迁移说明：
    在 V2→V3 灰度迁移中，DocGenerator 是第一个被切到事件驱动模式的 Agent，
    因为它只接收输入、产出文档，不和其他 Agent 交互，迁移风险最低。

    Args:
        llm_gateway: LLM 网关实例。
        tool_registry: 工具注册表（可选）。
    """

    REQUIRED_CONTEXT_KEYS = ["code_review_result", "test_result"]

    def __init__(
        self,
        llm_gateway: Any,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
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

        只提取审查结果和测试结果摘要，不接收原始代码内容。

        Args:
            context_snapshot: 完整的上下文快照。

        Returns:
            包含审查结果和测试结果的上下文子集。
        """
        return {k: context_snapshot[k] for k in self.REQUIRED_CONTEXT_KEYS if k in context_snapshot}

    def _build_downstream_context(
        self,
        original_snapshot: dict[str, Any],
        relevant_context: dict[str, Any],
        tool_results: list,
    ) -> dict[str, Any]:
        """构造下游 Agent 需要的上下文快照。

        文档生成通常是工作流的最后一步，下游只需要文档内容。

        Args:
            original_snapshot: 原始上下文快照。
            relevant_context: 当前 Agent 提取的上下文。
            tool_results: 工具执行结果。

        Returns:
            传递给下游 Agent 的上下文快照。
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
            task: 任务描述。

        Returns:
            消息列表。
        """
        return [
            {"role": "system", "content": "You are a documentation generator."},
            {"role": "user", "content": task},
        ]
