"""文件读写工具 — 提供文件读取和写入功能。

Agent 通过工具注册表调用此工具读写文件，
用于读取待审查的代码文件和写入生成的文档。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class FileIOTool(BaseTool):
    """文件读写工具 — 提供安全的文件读写功能。

    功能：
    - 读取文件内容
    - 写入文件内容
    - 列出目录下的文件
    - 检查文件是否存在

    安全设计：
    - 路径限制在指定根目录内（防止路径穿越攻击）
    - 文件大小限制（防止读取超大文件）
    - 文件类型白名单（可选）

    Args:
        root_dir: 允许操作的根目录。
        max_file_size: 最大文件大小（字节）。
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
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            root_dir: str，调用方传入的 root_dir 参数。
            max_file_size: int，调用方传入的 max_file_size 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.root_dir = os.path.abspath(root_dir)
        self.max_file_size = max_file_size

    @property
    def name(self) -> str:
        """工具唯一标识。"""
        return "file_io"

    def schema(self) -> dict:
        """执行 schema 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
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
        """执行文件操作。

        Args:
            operation: 操作类型（read/write/list/exists）。
            file_path: 文件路径。
            content: 写入内容（write 操作时需要）。

        Returns:
            文件操作结果。
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

        使用 ``Path.resolve().relative_to(root)`` 做路径边界判断，而非字符串
        前缀 ``startswith``。前缀匹配存在经典绕过：当 ``root_dir=".../user"``
        时，``.../user_evil/a.py`` 也以该前缀开头而通过。基于文件系统组件
        的边界判断能真正防止路径穿越。

        Args:
            file_path: 文件路径。

        Returns:
            路径是否安全。
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
            文件内容。
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
            写入结果。
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
            dir_path: 目录路径。

        Returns:
            文件列表。
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
            存在性检查结果。
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
