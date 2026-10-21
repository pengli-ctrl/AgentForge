"""安全扫描工具模块。"""

from __future__ import annotations

import logging
import re
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SecurityScanTool(BaseTool):
    """安全扫描工具 — 检测代码中的安全漏洞。

    Attributes:
        SECURITY_RULES: 安全规则。
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
        """初始化 SecurityScanTool。

        Args:
            rules_path: 规则路径。
        """
        self.rules_path = rules_path

    @property
    def name(self) -> str:
        """工具唯一标识。

        Returns:
            字符串结果。
        """
        return "security_scan"

    def schema(self) -> dict:
        """返回工具参数的结构定义。

        Returns:
            结构化结果字典。
        """
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
        """执行核心处理逻辑并返回结果。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
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
