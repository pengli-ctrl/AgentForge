"""
BaseTool 抽象基类 — 工具统一接口。

从 V1 PoC 阶段就认真设计的工具抽象层，后来直接被 V2/V3 继承，
省了大量重构成本。即使是最简单的 PoC，工具调用也不能直接写在业务代码里。

核心设计：
- 每个工具有 JSON Schema 描述参数格式，告诉 LLM 如何调用
- 异步执行，支持超时控制
- 标准化结果输出（ToolResult）
- 统一注册表管理（ToolRegistry）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    """工具执行结果的标准输出格式。

    Attributes:
        success: 执行是否成功
        output: 执行输出内容
        error: 失败时的错误信息
        metadata: 额外的元数据（耗时、资源使用等）
    """

    success: bool
    output: str
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """序列化为 JSON 字符串，用于注入 LLM 消息上下文。"""
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
    """工具统一接口 — V1 最值得设计的部分，后来直接被 V2/V3 继承。

    每个工具必须实现：
    - name: 工具唯一标识
    - schema: JSON Schema 描述参数格式，告诉 LLM 这个工具的参数格式
    - execute: 异步执行工具逻辑

    设计原则：
    - 工具调用逻辑不写在业务代码里，通过注册表统一管理
    - Schema 驱动：LLM 通过 schema 知道如何调用工具
    - 结果标准化：所有工具返回 ToolResult，便于统一处理
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识名称。"""
        ...

    @abstractmethod
    def schema(self) -> dict:
        """返回 JSON Schema，告诉 LLM 这个工具的参数格式。

        Returns:
            符合 OpenAI Function Calling 格式的 JSON Schema 字典。
        """
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """异步执行工具逻辑。

        Args:
            **kwargs: 工具参数，与 schema() 定义的格式一致。

        Returns:
            标准化的工具执行结果。
        """
        ...


class ToolRegistry:
    """统一工具注册表 — 管理 Agent 可用的所有工具。

    负责工具的注册、查询和执行，Agent 通过注册表统一调用工具，
    而不是直接持有工具实例。
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具实例。

        Args:
            tool: 实现 BaseTool 接口的工具实例。
        """
        self._tools[tool.name] = tool

    def get_schemas(self) -> list[dict]:
        """获取所有已注册工具的 JSON Schema 列表。

        Returns:
            工具 Schema 列表，用于传递给 LLM 的 tools 参数。
        """
        return [tool.schema() for tool in self._tools.values()]

    def get_tool_descriptions(self) -> str:
        """获取所有已注册工具的描述信息，用于注入 LLM System Prompt。

        Returns:
            工具描述文本，每行一个工具。
        """
        lines: list[str] = []
        for tool in self._tools.values():
            schema = tool.schema()
            desc = schema.get("description", "")
            lines.append(f"- {tool.name}: {desc}")
        return "\n".join(lines) if lines else "(no tools registered)"

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """执行指定工具。

        Args:
            name: 工具名称。
            arguments: 工具参数。

        Returns:
            工具执行结果。

        Raises:
            KeyError: 工具未注册。
        """
        if name not in self._tools:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool '{name}' not found in registry",
            )
        tool = self._tools[name]
        return await tool.execute(**arguments)
