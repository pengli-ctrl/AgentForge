"""生成工具模块。"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class DocGenerationTool(BaseTool):
    """生成工具相关组件。"""

    def __init__(self, output_dir: str = "./docs/generated") -> None:
        """初始化 DocGenerationTool。

        Args:
            output_dir: 输出目录。
        """
        self.output_dir = output_dir

    @property
    def name(self) -> str:
        """工具唯一标识。

        Returns:
            字符串结果。
        """
        return "doc_generation"

    def schema(self) -> dict:
        """返回工具参数的结构定义。

        Returns:
            结构化结果字典。
        """
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
        """执行核心处理逻辑并返回结果。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
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
