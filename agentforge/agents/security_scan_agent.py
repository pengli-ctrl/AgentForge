"""安全扫描智能体模块。"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.agent import Agent
from agentforge.core.base_tool import ToolRegistry

logger = logging.getLogger(__name__)


class SecurityScanAgent(Agent):
    """安全扫描智能体，识别风险并生成结构化安全发现。"""

    REQUIRED_CONTEXT_KEYS = ["code_content", "security_config"]

    def __init__(
        self,
        llm_gateway: Any,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        """初始化 SecurityScanAgent。

        Args:
            llm_gateway: LLM 网关实例。
            tool_registry: 工具注册表。
        """
        super().__init__(
            llm_gateway=llm_gateway,
            name="security-scan",
            tool_registry=tool_registry or ToolRegistry(),
            max_iterations=4,
            token_budget=6000,
        )

        self.prompt_template = (
            "你是一个专业的安全扫描助手。请严格基于以下代码进行安全分析。\\n\\n"
            "## 待扫描代码\\n{task}\\n\\n"
            "## 上下文信息\\n{context}\\n\\n"
            "## 安全扫描要求\\n"
            "1. 检测 SQL 注入、XSS、CSRF 等常见安全漏洞\\n"
            "2. 检测硬编码密钥、密码、Token\\n"
            "3. 检测敏感信息泄露（日志、错误信息）\\n"
            "4. 每个漏洞必须引用具体的代码行\\n"
            "5. 按严重程度分级：critical | warning | info\\n"
            "6. 输出结构化 JSON 格式\\n"
        )

    def _extract_context(self, context_snapshot: dict[str, Any]) -> dict[str, Any]:
        """从上下文快照中提取安全扫描需要的上下文。

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
            "security_scan_result": {
                "severity": "info",
                "has_vulnerabilities": False,
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
            {"role": "system", "content": "You are a professional security scanner."},
            {"role": "user", "content": task},
        ]
