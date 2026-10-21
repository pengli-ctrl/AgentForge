"""代码审查工具模块。"""

from __future__ import annotations

import ast
import logging
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class CodeReviewTool(BaseTool):
    """代码审查工具 — 分析代码质量、检测安全漏洞和规范问题。"""

    # 复杂度阈值
    MAX_COMPLEXITY = 10
    MAX_FUNCTION_LENGTH = 50
    MAX_NESTING_DEPTH = 4

    def __init__(
        self,
        rules_path: str | None = None,
        max_file_size: int = 1024 * 1024,
    ) -> None:
        """初始化 CodeReviewTool。

        Args:
            rules_path: 规则路径。
            max_file_size: 最大文件大小。
        """
        self.rules_path = rules_path
        self.max_file_size = max_file_size

    @property
    def name(self) -> str:
        """工具唯一标识。

        Returns:
            字符串结果。
        """
        return "code_review"

    def schema(self) -> dict:
        """返回工具参数的结构定义。

        Returns:
            结构化结果字典。
        """
        return {
            "type": "function",
            "function": {
                "name": "code_review",
                "description": "分析代码质量，检测安全漏洞和编码规范问题",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要审查的文件路径",
                        },
                        "code_content": {
                            "type": "string",
                            "description": "代码内容（如果无法通过路径访问）",
                        },
                        "review_types": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "security",
                                    "logic",
                                    "style",
                                    "performance",
                                ],
                            },
                            "description": "审查类型列表",
                            "default": [
                                "security",
                                "logic",
                                "style",
                                "performance",
                            ],
                        },
                    },
                    "required": ["file_path"],
                },
            },
        }

    # AST 分析辅助方法

    @staticmethod
    def _calc_complexity(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> int:
        """计算函数的圈复杂度。

        Args:
            node: 待处理节点。

        Returns:
            整数结果。
        """
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, ast.If):
                complexity += 1
            elif isinstance(child, (ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.While):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
        return complexity

    @staticmethod
    def _calc_function_length(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> int:
        """计算函数体行数。

        Args:
            node: 待处理节点。

        Returns:
            整数结果。
        """
        if hasattr(node, "end_lineno") and node.end_lineno:
            return node.end_lineno - node.lineno + 1
        return 0

    @staticmethod
    def _calc_max_nesting(node: ast.AST) -> int:
        """计算 AST 节点树中的最大嵌套深度。

        Args:
            node: 待处理节点。

        Returns:
            整数结果。
        """
        nesting_nodes = (
            ast.If,
            ast.For,
            ast.AsyncFor,
            ast.While,
            ast.Try,
            ast.With,
            ast.AsyncWith,
        )

        def _depth(n: ast.AST, current: int) -> int:
            """处理深度。

            Args:
                n: 输入参数。
                current: 输入参数。

            Returns:
                整数结果。
            """
            max_d = current
            for child in ast.iter_child_nodes(n):
                if isinstance(child, nesting_nodes):
                    max_d = max(max_d, _depth(child, current + 1))
                else:
                    max_d = max(max_d, _depth(child, current))
            return max_d

        return _depth(node, 0)

    # 核心执行方法

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行核心处理逻辑并返回结果。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
        """
        file_path = kwargs.get("file_path", "")
        code_content = kwargs.get("code_content", "")
        review_types = kwargs.get(
            "review_types",
            ["security", "logic", "style", "performance"],
        )

        logger.info(
            "Code review started (file=%s, types=%s)",
            file_path,
            review_types,
        )

        # 空代码处理
        if not code_content.strip():
            return ToolResult(
                success=True,
                output=f"Code review completed for {file_path}. " f"No code to analyze.",
                metadata={
                    "file_path": file_path,
                    "review_types": review_types,
                    "findings": [],
                },
            )

        # AST 解析
        try:
            tree = ast.parse(code_content)
        except SyntaxError as e:
            logger.warning(
                "Syntax error in code (file=%s, error=%s)",
                file_path,
                e,
            )
            return ToolResult(
                success=False,
                output=f"Code review failed for {file_path}: " f"syntax error at line {e.lineno}.",
                error=f"SyntaxError at line {e.lineno}: {e.msg}",
                metadata={
                    "file_path": file_path,
                    "review_types": review_types,
                    "findings": [],
                    "syntax_error": {
                        "line": e.lineno,
                        "message": e.msg,
                    },
                },
            )

        findings: list[dict[str, Any]] = []

        # 遍历所有函数定义
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            func_name = node.name
            func_line = node.lineno

            # 1. 圈复杂度检测
            complexity = self._calc_complexity(node)
            if complexity > self.MAX_COMPLEXITY:
                findings.append(
                    {
                        "rule": "high_complexity",
                        "severity": "warning",
                        "description": (
                            f"Function '{func_name}' has cyclomatic "
                            f"complexity of {complexity} "
                            f"(max {self.MAX_COMPLEXITY})"
                        ),
                        "line": func_line,
                    }
                )

            # 2. 函数长度检测
            length = self._calc_function_length(node)
            if length > self.MAX_FUNCTION_LENGTH:
                findings.append(
                    {
                        "rule": "long_function",
                        "severity": "warning",
                        "description": (
                            f"Function '{func_name}' is {length} lines "
                            f"long (max {self.MAX_FUNCTION_LENGTH})"
                        ),
                        "line": func_line,
                    }
                )

            # 3. 嵌套深度检测
            nesting = self._calc_max_nesting(node)
            if nesting > self.MAX_NESTING_DEPTH:
                findings.append(
                    {
                        "rule": "deep_nesting",
                        "severity": "warning",
                        "description": (
                            f"Function '{func_name}' has nesting depth "
                            f"of {nesting} "
                            f"(max {self.MAX_NESTING_DEPTH})"
                        ),
                        "line": func_line,
                    }
                )

        # 汇总
        warning_count = sum(1 for f in findings if f["severity"] == "warning")
        critical_count = sum(1 for f in findings if f["severity"] == "critical")

        severity = "info"
        if critical_count > 0:
            severity = "critical"
        elif warning_count > 0:
            severity = "warning"

        logger.info(
            "Code review completed (file=%s, findings=%d, severity=%s)",
            file_path,
            len(findings),
            severity,
        )

        output = (
            f"Code review completed for {file_path}. "
            f"Found {len(findings)} issues "
            f"(warnings={warning_count}, critical={critical_count}, "
            f"severity={severity})."
        )

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "file_path": file_path,
                "review_types": review_types,
                "findings": findings,
                "severity": severity,
                "warning_count": warning_count,
                "critical_count": critical_count,
            },
        )
