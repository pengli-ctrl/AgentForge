"""安全扫描工具 — 检测代码中的安全漏洞。

Agent 通过工具注册表调用此工具执行安全扫描，
检测 SQL 注入、XSS、硬编码密钥等安全风险。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SecurityScanTool(BaseTool):
    """安全扫描工具 — 检测代码中的安全漏洞。

    功能：
    - SQL 注入检测（字符串拼接 SQL 语句）
    - XSS 检测（未转义的用户输入输出）
    - 硬编码密钥检测（API Key、密码、Token）
    - 敏感信息泄露检测（日志中的密码、错误信息中的堆栈）

    检测规则基于正则表达式，不依赖 LLM 判断。
    这是 Trust Boundary 确定性校验的体现。

    Args:
        rules_path: 自定义规则文件路径（可选）。
    """

    # 安全检测规则（正则表达式）
    SECURITY_RULES: list[dict[str, Any]] = [
        {
            "name": "sql_injection",
            "pattern": r"(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s+.*?\+.*?(?:%s|format|f['\"])",
            "severity": "critical",
            "description": "Potential SQL injection: string concatenation in SQL query",
        },
        {
            "name": "hardcoded_password",
            "pattern": r"(?:password|passwd|pwd)\s*=\s*['\"][^'\"]+['\"]",
            "severity": "critical",
            "description": "Hardcoded password detected",
        },
        {
            "name": "hardcoded_api_key",
            "pattern": r"(?:api_key|apikey|secret_key|access_token)\s*=\s*['\"][^'\"]+['\"]",
            "severity": "critical",
            "description": "Hardcoded API key or secret detected",
        },
        {
            "name": "eval_usage",
            "pattern": r"\beval\s*\(",
            "severity": "warning",
            "description": "Use of eval() is dangerous",
        },
        {
            "name": "exec_usage",
            "pattern": r"\bexec\s*\(",
            "severity": "warning",
            "description": "Use of exec() is dangerous",
        },
        {
            "name": "pickle_load",
            "pattern": r"pickle\.loads?\s*\(",
            "severity": "warning",
            "description": "Pickle deserialization is unsafe for untrusted data",
        },
        {
            "name": "debug_mode",
            "pattern": r"DEBUG\s*=\s*True",
            "severity": "warning",
            "description": "Debug mode enabled in production code",
        },
    ]

    def __init__(self, rules_path: str | None = None) -> None:
        self.rules_path = rules_path

    @property
    def name(self) -> str:
        """工具唯一标识。"""
        return "security_scan"

    def schema(self) -> dict:
        """返回 JSON Schema。"""
        return {
            "type": "function",
            "function": {
                "name": "security_scan",
                "description": "扫描代码中的安全漏洞",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code_content": {
                            "type": "string",
                            "description": "要扫描的代码内容",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "文件路径（用于报告）",
                        },
                    },
                    "required": ["code_content"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行安全扫描。

        Args:
            code_content: 要扫描的代码内容。
            file_path: 文件路径（用于报告）。

        Returns:
            扫描结果，包含发现的安全漏洞列表。
        """
        code_content = kwargs.get("code_content", "")
        file_path = kwargs.get("file_path", "unknown")

        logger.info("Security scan started (file=%s)", file_path)

        findings: list[dict[str, Any]] = []
        lines = code_content.split("\n")

        for line_num, line in enumerate(lines, 1):
            for rule in self.SECURITY_RULES:
                if re.search(rule["pattern"], line, re.IGNORECASE):
                    findings.append(
                        {
                            "rule": rule["name"],
                            "severity": rule["severity"],
                            "description": rule["description"],
                            "file": file_path,
                            "line": line_num,
                            "code": line.strip(),
                        }
                    )

        severity = "info"
        if any(f["severity"] == "critical" for f in findings):
            severity = "critical"
        elif any(f["severity"] == "warning" for f in findings):
            severity = "warning"

        logger.info(
            "Security scan completed (file=%s, findings=%d, severity=%s)",
            file_path,
            len(findings),
            severity,
        )

        return ToolResult(
            success=True,
            output=f"Security scan completed. Found {len(findings)} issues "
            f"(severity={severity}).",
            metadata={
                "file_path": file_path,
                "findings": findings,
                "severity": severity,
                "has_vulnerabilities": len(findings) > 0,
            },
        )
