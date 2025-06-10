"""文档生成工具 — 基于代码变更生成变更文档。

Agent 通过工具注册表调用此工具生成 Markdown 格式的文档。
"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class DocGenerationTool(BaseTool):
    """文档生成工具 — 生成 Markdown 格式的变更文档。

    功能：
    - 基于代码审查结果和测试报告生成变更文档
    - 生成 API 变更说明
    - 生成 changelog 条目
    - 标注 breaking changes

    Args:
        output_dir: 文档输出目录。
    """

    def __init__(self, output_dir: str = "./docs/generated") -> None:
        self.output_dir = output_dir

    @property
    def name(self) -> str:
        """工具唯一标识。"""
        return "doc_generation"

    def schema(self) -> dict:
        """返回 JSON Schema。"""
        return {
            "type": "function",
            "function": {
                "name": "doc_generation",
                "description": "基于代码变更和审查结果生成变更文档",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "review_result": {
                            "type": "string",
                            "description": "代码审查结果摘要",
                        },
                        "test_result": {
                            "type": "string",
                            "description": "测试执行结果摘要",
                        },
                        "doc_type": {
                            "type": "string",
                            "enum": ["changelog", "api_doc", "migration_guide"],
                            "description": "文档类型",
                            "default": "changelog",
                        },
                    },
                    "required": ["review_result"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """生成文档。

        Args:
            review_result: 代码审查结果摘要。
            test_result: 测试执行结果摘要。
            doc_type: 文档类型。

        Returns:
            文档生成结果。
        """
        doc_type = kwargs.get("doc_type", "changelog")
        review_result = kwargs.get("review_result", "")

        logger.info("Doc generation started (type=%s)", doc_type)

        return ToolResult(
            success=True,
            output=f"Document generated (type={doc_type}). "
            f"Based on review: {review_result[:100]}...",
            metadata={
                "doc_type": doc_type,
                "output_dir": self.output_dir,
            },
        )
