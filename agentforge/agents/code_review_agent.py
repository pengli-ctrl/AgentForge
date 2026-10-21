"""代码审查智能体模块。"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.agent import Agent
from agentforge.core.base_tool import ToolRegistry
from agentforge.tools.code_review_tool import CodeReviewTool

logger = logging.getLogger(__name__)


class CodeReviewAgent(Agent):
    """代码审查智能体，分析代码质量并输出结构化审查意见。"""

    # 该 Agent 需要从 context_snapshot 中提取的上下文键
    REQUIRED_CONTEXT_KEYS = ["code_content", "review_config"]

    def __init__(
        self,
        llm_gateway: Any,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        """初始化 CodeReviewAgent。

        Args:
            llm_gateway: LLM 网关实例。
            tool_registry: 工具注册表。
        """
        registry = tool_registry or ToolRegistry()
        registry.register(CodeReviewTool())

        super().__init__(
            llm_gateway=llm_gateway,
            name="code-review",
            tool_registry=registry,
            max_iterations=5,
            token_budget=8000,
        )

        self.prompt_template = (
            "你是一个专业的代码审查助手。请严格基于以下代码进行审查。\n\n"
            "## 待审查代码\n{task}\n\n"
            "## 上下文信息\n{context}\n\n"
            "## 审查要求\n"
            "1. 仅基于以上代码进行审查，不要使用训练知识补充\n"
            "2. 每个审查意见必须引用具体的代码行\n"
            "3. 按严重程度分级：error | warning | info\n"
            "4. 输出结构化 JSON 格式\n"
        )

    def _extract_context(self, context_snapshot: dict[str, Any]) -> dict[str, Any]:
        """从上下文快照中提取代码审查需要的上下文。

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
            "code_review_result": {
                "severity": "info",  # 实际由 LLM 输出决定
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
            {"role": "system", "content": "You are a professional code reviewer."},
            {"role": "user", "content": task},
        ]
