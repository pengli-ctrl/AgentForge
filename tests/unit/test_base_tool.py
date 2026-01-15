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
        """执行 name 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
        """
        return "echo"

    def schema(self) -> dict:
        """执行 schema 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
        """
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
        """执行 execute 对应的逻辑，并返回处理结果。

        Args:
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            ToolResult，函数执行后的结果。
        """
        msg = kwargs.get("message", "")
        return ToolResult(success=True, output=f"echo: {msg}")


class FailTool(BaseTool):
    """总是失败的工具。"""

    @property
    def name(self) -> str:
        """执行 name 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
        """
        return "fail_tool"

    def schema(self) -> dict:
        """执行 schema 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
        """
        return {"name": "fail_tool", "description": "Always fails", "parameters": {}}

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行 execute 对应的逻辑，并返回处理结果。

        Args:
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            ToolResult，函数执行后的结果。
        """
        return ToolResult(success=False, output="", error="intentional failure")


class TestToolResult:
    """TestToolResult。

    TestToolResult 组织一组相关测试，覆盖正常流程、边界条件和回归场景。

    主要成员：
    - 方法 test_success_result()。
    - 方法 test_failure_result()。
    - 方法 test_to_json_serializes_correctly()。
    - 方法 test_to_json_with_error()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def test_success_result(self) -> None:
        """验证 success_result 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        result = ToolResult(success=True, output="ok")
        assert result.success is True
        assert result.output == "ok"
        assert result.error is None
        assert result.metadata == {}

    def test_failure_result(self) -> None:
        """验证 failure_result 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        result = ToolResult(success=False, output="", error="boom")
        assert result.success is False
        assert result.error == "boom"

    def test_to_json_serializes_correctly(self) -> None:
        """验证 to_json_serializes_correctly 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        result = ToolResult(success=True, output="hello", error=None)
        data = json.loads(result.to_json())
        assert data["success"] is True
        assert data["output"] == "hello"
        assert data["error"] is None

    def test_to_json_with_error(self) -> None:
        """验证 to_json_with_error 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        result = ToolResult(success=False, output="", error="fail")
        data = json.loads(result.to_json())
        assert data["success"] is False
        assert data["error"] == "fail"


class TestBaseTool:
    """BaseTool 抽象基类测试。"""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """验证 cannot_instantiate_abstract_class 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        with pytest.raises(TypeError):
            BaseTool()  # type: ignore[abstract]

    def test_concrete_tool_has_name(self) -> None:
        """验证 concrete_tool_has_name 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        tool = EchoTool()
        assert tool.name == "echo"

    def test_concrete_tool_has_schema(self) -> None:
        """验证 concrete_tool_has_schema 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        tool = EchoTool()
        schema = tool.schema()
        assert schema["name"] == "echo"
        assert "parameters" in schema

    @pytest.mark.asyncio
    async def test_concrete_tool_execute(self) -> None:
        """验证 concrete_tool_execute 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        tool = EchoTool()
        result = await tool.execute(message="hello world")
        assert result.success is True
        assert result.output == "echo: hello world"


class TestToolRegistry:
    """TestToolRegistry。

    TestToolRegistry 组织一组相关测试，覆盖正常流程、边界条件和回归场景。

    主要成员：
    - 方法 test_register_and_get_schemas()。
    - 方法 test_register_multiple_tools()。
    - 方法 test_execute_registered_tool()。
    - 方法 test_execute_unregistered_tool_returns_error()。
    - 方法 test_execute_fail_tool()。
    - 方法 test_overwrite_tool_on_re_register()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def test_register_and_get_schemas(self) -> None:
        """验证 register_and_get_schemas 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        registry = ToolRegistry()
        registry.register(EchoTool())
        schemas = registry.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "echo"

    def test_register_multiple_tools(self) -> None:
        """验证 register_multiple_tools 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.register(FailTool())
        assert len(registry.get_schemas()) == 2

    @pytest.mark.asyncio
    async def test_execute_registered_tool(self) -> None:
        """验证 execute_registered_tool 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        registry = ToolRegistry()
        registry.register(EchoTool())
        result = await registry.execute("echo", {"message": "test"})
        assert result.success is True
        assert "test" in result.output

    @pytest.mark.asyncio
    async def test_execute_unregistered_tool_returns_error(self) -> None:
        """验证 execute_unregistered_tool_returns_error 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        registry = ToolRegistry()
        result = await registry.execute("nonexistent", {})
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_fail_tool(self) -> None:
        """验证 execute_fail_tool 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
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
