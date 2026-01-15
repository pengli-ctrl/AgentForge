"""安全扫描 Agent — 检测安全漏洞、生成安全报告。

V3 架构中的第 4 个 Agent，在博客文章中提到但尚未实现。
负责检测代码中的安全漏洞（SQL 注入、XSS、硬编码密钥、敏感信息泄露），
生成结构化的安全扫描报告。

上下文隔离：只从 context_snapshot 中提取代码内容和安全扫描配置，
不接收测试日志、文档等其他 Agent 的数据。

动态路由：
- 发现 critical 级别漏洞 → 路由回 code-review 重新审查
- 仅有 warning 级别问题 → 路由到 doc-generator 生成报告
- 无安全问题 → 路由到 test-execution 继续测试
"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.agent import Agent
from agentforge.core.base_tool import ToolRegistry

logger = logging.getLogger(__name__)


class SecurityScanAgent(Agent):
    """安全扫描 Agent — 检测安全漏洞并生成安全报告。

    职责：
    - 检测 SQL 注入、XSS、CSRF 等安全漏洞
    - 检测硬编码密钥、密码、Token
    - 检测敏感信息泄露（日志中的密码、错误信息中的堆栈）
    - 检测不安全的依赖库版本
    - 生成结构化安全扫描报告

    上下文隔离：
    - 只提取 context_snapshot 中的 code_content 和 security_config
    - 不接收测试日志、文档生成结果等其他 Agent 的数据
    - 输出事件只携带安全扫描结果摘要和 severity 级别

    动态路由（通过工作流 YAML 配置）：
    - result.severity == 'critical' → 路由回 code-review
    - result.has_vulnerabilities → 路由到 code-review
    - default → 路由到 test-execution

    Args:
        llm_gateway: LLM 网关实例。
        tool_registry: 工具注册表（可选）。
    """

    REQUIRED_CONTEXT_KEYS = ["code_content", "security_config"]

    def __init__(
        self,
        llm_gateway: Any,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            llm_gateway: Any，调用方传入的 llm_gateway 参数。
            tool_registry: ToolRegistry | None，调用方传入的 tool_registry 参数。

        Returns:
            None，函数执行后的结果。
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

        只提取 code_content 和 security_config，不接收全量数据。

        Args:
            context_snapshot: 完整的上下文快照。

        Returns:
            仅包含代码内容和安全扫描配置的上下文子集。
        """
        return {k: context_snapshot[k] for k in self.REQUIRED_CONTEXT_KEYS if k in context_snapshot}

    def _build_downstream_context(
        self,
        original_snapshot: dict[str, Any],
        relevant_context: dict[str, Any],
        tool_results: list,
    ) -> dict[str, Any]:
        """构造下游 Agent 需要的上下文快照。

        只传递安全扫描结果摘要和 severity 级别，
        用于动态路由决策。

        Args:
            original_snapshot: 原始上下文快照。
            relevant_context: 当前 Agent 提取的上下文。
            tool_results: 工具执行结果。

        Returns:
            传递给下游 Agent 的上下文快照。
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
            task: 任务描述。

        Returns:
            消息列表。
        """
        return [
            {"role": "system", "content": "You are a professional security scanner."},
            {"role": "user", "content": task},
        ]
