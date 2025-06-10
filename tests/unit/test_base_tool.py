"""BaseTool 单元测试 — 工具抽象基类。

测试要点：工具注册、JSON Schema生成、执行接口、结果标准化。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agentforge.core.base_tool import BaseTool, ToolRegistry, ToolResult


class EchoTool(BaseTool):
    """回声工具 — 返回输入参数。"""

    @property
    def name(self) -> str:
        return "echo"

    def schema(self) -> dict:
        return {
            "name": "echo",
            "description": "Echoes back the input message",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Message to echo"},
                },
                "required": ["message"],
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        msg = kwargs.get("message", "")
        return ToolResult(success=True, output=f"echo: {msg}")


class FailTool(BaseTool):
    """总是失败的工具。"""

    @property
    def name(self) -> str:
        return "fail_tool"

    def schema(self) -> dict:
        return {"name": "fail_tool", "description": "Always fails", "parameters": {}}

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(success=False, output="", error="intentional failure")


class TestToolResult:
    """ToolResult 测试。"""

    def test_success_result(self) -> None:
        result = ToolResult(success=True, output="ok")
        assert result.success is True
        assert result.output == "ok"
        assert result.error is None
        assert result.metadata == {}

    def test_failure_result(self) -> None:
        result = ToolResult(success=False, output="", error="boom")
        assert result.success is False
        assert result.error == "boom"

    def test_to_json_serializes_correctly(self) -> None:
        result = ToolResult(success=True, output="hello", error=None)
        data = json.loads(result.to_json())
        assert data["success"] is True
        assert data["output"] == "hello"
        assert data["error"] is None

    def test_to_json_with_error(self) -> None:
        result = ToolResult(success=False, output="", error="fail")
        data = json.loads(result.to_json())
        assert data["success"] is False
        assert data["error"] == "fail"


class TestBaseTool:
    """BaseTool 抽象基类测试。"""

    def test_cannot_instantiate_abstract_class(self) -> None:
        with pytest.raises(TypeError):
            BaseTool()  # type: ignore[abstract]

    def test_concrete_tool_has_name(self) -> None:
        tool = EchoTool()
        assert tool.name == "echo"

    def test_concrete_tool_has_schema(self) -> None:
        tool = EchoTool()
        schema = tool.schema()
        assert schema["name"] == "echo"
        assert "parameters" in schema

    @pytest.mark.asyncio
    async def test_concrete_tool_execute(self) -> None:
        tool = EchoTool()
        result = await tool.execute(message="hello world")
        assert result.success is True
        assert result.output == "echo: hello world"


class TestToolRegistry:
    """ToolRegistry 测试。"""

    def test_register_and_get_schemas(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        schemas = registry.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "echo"

    def test_register_multiple_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.register(FailTool())
        assert len(registry.get_schemas()) == 2

    @pytest.mark.asyncio
    async def test_execute_registered_tool(self) -> None:
        registry = ToolRegistry()
        registry.register(EchoTool())
        result = await registry.execute("echo", {"message": "test"})
        assert result.success is True
        assert "test" in result.output

    @pytest.mark.asyncio
    async def test_execute_unregistered_tool_returns_error(self) -> None:
        registry = ToolRegistry()
        result = await registry.execute("nonexistent", {})
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_fail_tool(self) -> None:
        registry = ToolRegistry()
        registry.register(FailTool())
        result = await registry.execute("fail_tool", {})
        assert result.success is False
        assert result.error == "intentional failure"

    def test_overwrite_tool_on_re_register(self) -> None:
        """同名工具重新注册会覆盖旧的。"""
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.register(EchoTool())  # 再次注册
        assert len(registry.get_schemas()) == 1
