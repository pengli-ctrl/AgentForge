"""
代码审查 Agent — 分析代码质量、检测安全漏洞、生成审查报告。

V3 架构中的核心 Agent，通过事件总线接收代码审查任务，
利用 LLM + 工具调用完成代码分析，输出结构化审查结果。

上下文隔离：只从 context_snapshot 中提取代码内容和审查配置，
不接收测试日志、文档等其他 Agent 的数据。
"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.agent import Agent
from agentforge.core.base_tool import ToolRegistry
from agentforge.tools.code_review_tool import CodeReviewTool

logger = logging.getLogger(__name__)


class CodeReviewAgent(Agent):
    """代码审查 Agent — 分析代码质量并生成审查报告。

    职责：
    - 分析代码的圈复杂度、函数长度、重复代码
    - 检测安全漏洞（SQL 注入、XSS、硬编码密钥）
    - 检查编码规范（命名、注释、import 顺序）
    - 生成结构化审查报告

    上下文隔离：
    - 只提取 context_snapshot 中的 code_content 和 review_config
    - 不接收测试日志、文档生成结果等其他 Agent 的数据
    - 输出事件只携带审查结果摘要和 severity 级别

    Args:
        llm_gateway: LLM 网关实例。
        tool_registry: 工具注册表（可选，不传则使用默认工具集）。
    """

    # 该 Agent 需要从 context_snapshot 中提取的上下文键
    REQUIRED_CONTEXT_KEYS = ["code_content", "review_config"]

    def __init__(
        self,
        llm_gateway: Any,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
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

        只提取 code_content 和 review_config，不接收全量数据。
        这是 V3 状态隔离的核心 — 解决 V2 中 context 无限膨胀的问题。

        Args:
            context_snapshot: 完整的上下文快照。

        Returns:
            仅包含代码内容和审查配置的上下文子集。
        """
        return {k: context_snapshot[k] for k in self.REQUIRED_CONTEXT_KEYS if k in context_snapshot}

    def _build_downstream_context(
        self,
        original_snapshot: dict[str, Any],
        relevant_context: dict[str, Any],
        tool_results: list,
    ) -> dict[str, Any]:
        """构造下游 Agent 需要的上下文快照。

        只传递审查结果摘要和 severity 级别，
        不传递原始代码内容（下游不需要）。

        Args:
            original_snapshot: 原始上下文快照。
            relevant_context: 当前 Agent 提取的上下文。
            tool_results: 工具执行结果。

        Returns:
            传递给下游 Agent 的上下文快照。
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
            task: 任务描述。

        Returns:
            消息列表。
        """
        return [
            {"role": "system", "content": "You are a professional code reviewer."},
            {"role": "user", "content": task},
        ]
