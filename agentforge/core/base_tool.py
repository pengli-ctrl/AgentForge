"""基础工具模块。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    """工具执行结果的标准输出格式。

    Attributes:
        success: 是否成功。
        output: 输出。
        error: 错误信息。
        metadata: 附加元数据。
    """

    success: bool
    output: str
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """转换JSON。

        Returns:
            字符串结果。
        """
        import json

        return json.dumps(
            {
                "success": self.success,
                "output": self.output,
                "error": self.error,
            },
            ensure_ascii=False,
        )


class BaseTool(ABC):
    """工具统一接口 — V1 最值得设计的部分，后来直接被 V2/V3 继承。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识名称。

        Returns:
            字符串结果。
        """
        ...

    @abstractmethod
    def schema(self) -> dict:
        """返回工具参数的结构定义。

        Returns:
            结构化结果字典。
        """
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行核心处理逻辑并返回结果。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
        """
        ...


class ToolRegistry:
    """工具注册表。"""

    def __init__(self) -> None:
        """初始化 ToolRegistry。"""
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具实例。

        Args:
            tool: 工具。
        """
        self._tools[tool.name] = tool

    def get_schemas(self) -> list[dict]:
        """获取结构定义。

        Returns:
            结果列表。
        """
        return [tool.schema() for tool in self._tools.values()]

    def get_tool_descriptions(self) -> str:
        """获取工具描述。

        Returns:
            字符串结果。
        """
        lines: list[str] = []
        for tool in self._tools.values():
            schema = tool.schema()
            desc = schema.get("description", "")
            lines.append(f"- {tool.name}: {desc}")
        return "\n".join(lines) if lines else "(no tools registered)"

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """执行核心处理逻辑并返回结果。

        Args:
            name: 资源或对象名称。
            arguments: 参数。

        Returns:
            工具结果结果。
        """
        if name not in self._tools:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool '{name}' not found in registry",
            )
        tool = self._tools[name]
        return await tool.execute(**arguments)
