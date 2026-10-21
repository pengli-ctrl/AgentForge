"""文件工具模块。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class FileIOTool(BaseTool):
    """文件读写工具 — 提供安全的文件读写功能。

    Attributes:
        ALLOWED_EXTENSIONS: 允许。
    """

    # 允许的文件扩展名（空集合表示不限制）
    ALLOWED_EXTENSIONS: set[str] = {
        ".py",
        ".js",
        ".ts",
        ".java",
        ".go",
        ".rs",
        ".yaml",
        ".yml",
        ".json",
        ".xml",
        ".toml",
        ".md",
        ".txt",
        ".rst",
        ".sql",
        ".sh",
        ".dockerfile",
    }

    def __init__(
        self,
        root_dir: str = ".",
        max_file_size: int = 10 * 1024 * 1024,
    ) -> None:
        """初始化 FileIOTool。

        Args:
            root_dir: 根。
            max_file_size: 最大文件大小。
        """
        self.root_dir = os.path.abspath(root_dir)
        self.max_file_size = max_file_size

    @property
    def name(self) -> str:
        """工具唯一标识。

        Returns:
            字符串结果。
        """
        return "file_io"

    def schema(self) -> dict:
        """返回工具参数的结构定义。

        Returns:
            结构化结果字典。
        """
        return {
            "type": "function",
            "function": {
                "name": "file_io",
                "description": "读写文件操作",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["read", "write", "list", "exists"],
                            "description": "文件操作类型",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "文件路径",
                        },
                        "content": {
                            "type": "string",
                            "description": "写入内容（write 操作时需要）",
                        },
                    },
                    "required": ["operation", "file_path"],
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
        operation = kwargs.get("operation", "")
        file_path = kwargs.get("file_path", "")

        logger.info("File IO: %s (path=%s)", operation, file_path)

        if operation == "read":
            return await self._read_file(file_path)
        elif operation == "write":
            content = kwargs.get("content", "")
            return await self._write_file(file_path, content)
        elif operation == "list":
            return await self._list_dir(file_path)
        elif operation == "exists":
            return await self._exists(file_path)
        else:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown operation: {operation}",
            )

    def _validate_path(self, file_path: str) -> bool:
        """验证文件路径是否安全（在根目录内）。

        Args:
            file_path: 文件路径。

        Returns:
            操作是否成功。
        """
        root = Path(self.root_dir).resolve()

        if os.path.isabs(file_path):
            target = Path(file_path).resolve()
        else:
            target = (root / file_path).resolve()

        try:
            target.relative_to(root)
            return True
        except ValueError:
            return False

    async def _read_file(self, file_path: str) -> ToolResult:
        """读取文件内容。

        Args:
            file_path: 文件路径。

        Returns:
            工具结果结果。
        """
        if not self._validate_path(file_path):
            return ToolResult(success=False, output="", error="Path outside allowed root directory")

        abs_path = os.path.join(self.root_dir, file_path)
        if not os.path.exists(abs_path):
            return ToolResult(success=False, output="", error=f"File not found: {file_path}")

        file_size = os.path.getsize(abs_path)
        if file_size > self.max_file_size:
            return ToolResult(
                success=False,
                output="",
                error=f"File too large: {file_size} bytes (max: {self.max_file_size})",
            )

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
            return ToolResult(success=True, output=content)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    async def _write_file(self, file_path: str, content: str) -> ToolResult:
        """写入文件内容。

        Args:
            file_path: 文件路径。
            content: 写入内容。

        Returns:
            工具结果结果。
        """
        if not self._validate_path(file_path):
            return ToolResult(success=False, output="", error="Path outside allowed root directory")

        abs_path = os.path.join(self.root_dir, file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(
                success=True,
                output=f"File written: {file_path} ({len(content)} bytes)",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    async def _list_dir(self, dir_path: str) -> ToolResult:
        """列出目录内容。

        Args:
            dir_path: 路径。

        Returns:
            工具结果结果。
        """
        if not self._validate_path(dir_path):
            return ToolResult(success=False, output="", error="Path outside allowed root directory")

        abs_path = os.path.join(self.root_dir, dir_path)
        if not os.path.isdir(abs_path):
            return ToolResult(success=False, output="", error=f"Not a directory: {dir_path}")

        try:
            entries = os.listdir(abs_path)
            return ToolResult(
                success=True,
                output="\n".join(entries),
                metadata={"entries": entries, "count": len(entries)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    async def _exists(self, file_path: str) -> ToolResult:
        """检查文件是否存在。

        Args:
            file_path: 文件路径。

        Returns:
            工具结果结果。
        """
        if not self._validate_path(file_path):
            return ToolResult(success=False, output="", error="Path outside allowed root directory")

        abs_path = os.path.join(self.root_dir, file_path)
        exists = os.path.exists(abs_path)
        return ToolResult(
            success=True,
            output=str(exists),
            metadata={"exists": exists},
        )
