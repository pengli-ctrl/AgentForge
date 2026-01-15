"""V1 AgentEngine 单元测试 — ReAct 循环。

测试要点：思考-行动-观察循环、工具调用、终止条件、错误处理。
"""

from __future__ import annotations

from typing import Any

import pytest

from agentforge.core.base_tool import BaseTool, ToolResult
from agentforge.core.v1_agent_engine import AgentEngine, AgentResult
from agentforge.llm.gateway import LLMResponse, ToolCall


class StubTool(BaseTool):
    """测试用 Stub 工具。"""

    @property
    def name(self) -> str:
        """执行 name 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
        """
        return "stub_tool"

    def schema(self) -> dict:
        """执行 schema 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
        """
        return {
            "name": "stub_tool",
            "description": "A stub tool for testing",
            "parameters": {"type": "object", "properties": {}},
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行 execute 对应的逻辑，并返回处理结果。

        Args:
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            ToolResult，函数执行后的结果。
        """
        return ToolResult(success=True, output="stub executed")


class TestAgentResult:
    """AgentResult 数据类测试。"""

    def test_defaults(self) -> None:
        """验证 defaults 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        result = AgentResult(output="done")
        assert result.output == "done"
        assert result.iterations == 0
        assert result.tool_calls == []
        assert result.token_usage == 0


class TestAgentEngineInit:
    """初始化测试。"""

    def test_init_with_gateway(self, mock_llm: Any) -> None:
        """验证 init_with_gateway 对应的业务行为、边界条件和回归场景。

        Args:
            mock_llm: Any，调用方传入的 mock_llm 参数。

        Returns:
            None，函数执行后的结果。
        """
        engine = AgentEngine(llm_gateway=mock_llm)
        assert engine.llm is mock_llm
        assert engine.max_iterations == 5
        assert engine.token_budget == 8000

    def test_custom_max_iterations(self, mock_llm: Any) -> None:
        """验证 custom_max_iterations 对应的业务行为、边界条件和回归场景。

        Args:
            mock_llm: Any，调用方传入的 mock_llm 参数。

        Returns:
            None，函数执行后的结果。
        """
        engine = AgentEngine(llm_gateway=mock_llm, max_iterations=3)
        assert engine.max_iterations == 3


class TestToolRegistration:
    """工具注册测试。"""

    def test_register_tool(self, mock_llm: Any) -> None:
        """验证 register_tool 对应的业务行为、边界条件和回归场景。

        Args:
            mock_llm: Any，调用方传入的 mock_llm 参数。

        Returns:
            None，函数执行后的结果。
        """
        engine = AgentEngine(llm_gateway=mock_llm)
        tool = StubTool()
        engine.register_tool(tool)
        schemas = engine.tool_registry.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "stub_tool"


class TestReActLoop:
    """ReAct 循环执行测试。"""

    @pytest.mark.asyncio
    async def test_immediate_answer_no_tool_calls(self, mock_llm: Any) -> None:
        """LLM 第一轮就返回答案，不调用工具。"""
        mock_llm._responses = [
            LLMResponse(
                content="Code looks good.",
                model="mock-model",
                usage={"prompt_tokens": 100, "completion_tokens": 20},
            )
        ]
        engine = AgentEngine(llm_gateway=mock_llm, max_iterations=5)
        result = await engine.execute("Review this code")

        assert isinstance(result, AgentResult)
        assert result.output == "Code looks good."
        assert result.iterations == 1
        assert result.tool_calls == []
        assert mock_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_tool_call_then_answer(self, mock_llm: Any) -> None:
        """LLM 先调用工具，再返回答案。"""
        mock_llm._responses = [
            LLMResponse(
                content="",
                has_tool_calls=True,
                tool_calls=[ToolCall(name="stub_tool", arguments={})],
                model="mock-model",
                usage={"prompt_tokens": 50, "completion_tokens": 10},
            ),
            LLMResponse(
                content="Analysis complete based on tool output.",
                model="mock-model",
                usage={"prompt_tokens": 80, "completion_tokens": 30},
            ),
        ]
        engine = AgentEngine(llm_gateway=mock_llm, max_iterations=5)
        engine.register_tool(StubTool())
        result = await engine.execute("Review this code")

        assert result.output == "Analysis complete based on tool output."
        assert result.iterations == 2
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool"] == "stub_tool"
        assert result.tool_calls[0]["success"] is True

    @pytest.mark.asyncio
    async def test_max_iterations_reached(self, mock_llm: Any) -> None:
        """达到最大迭代次数时返回占位输出。"""
        # 每轮都返回工具调用，永不给出最终答案
        mock_llm._responses = [
            LLMResponse(
                content="",
                has_tool_calls=True,
                tool_calls=[ToolCall(name="stub_tool", arguments={})],
                model="mock-model",
                usage={"prompt_tokens": 50, "completion_tokens": 10},
            )
            for _ in range(10)
        ]
        engine = AgentEngine(llm_gateway=mock_llm, max_iterations=3)
        engine.register_tool(StubTool())
        result = await engine.execute("Review this code")

        assert result.output == "[max iterations reached]"
        assert result.iterations == 3
        assert len(result.tool_calls) == 3

    @pytest.mark.asyncio
    async def test_token_usage_accumulated(self, mock_llm: Any) -> None:
        """Token 使用量累加。"""
        mock_llm._responses = [
            LLMResponse(
                content="",
                has_tool_calls=True,
                tool_calls=[ToolCall(name="stub_tool", arguments={})],
                model="mock-model",
                usage={"prompt_tokens": 100, "completion_tokens": 50},
            ),
            LLMResponse(
                content="Done.",
                model="mock-model",
                usage={"prompt_tokens": 200, "completion_tokens": 100},
            ),
        ]
        engine = AgentEngine(llm_gateway=mock_llm, max_iterations=5)
        engine.register_tool(StubTool())
        result = await engine.execute("Review code")

        assert result.token_usage == 450  # 说明：该步骤用于实现上述逻辑并保证行为稳定。


class TestBuildMessages:
    """消息构建测试。"""

    def test_initial_messages_contain_system_and_user(self, mock_llm: Any) -> None:
        """验证 initial_messages_contain_system_and_user 对应的业务行为、边界条件和回归场景。

        Args:
            mock_llm: Any，调用方传入的 mock_llm 参数。

        Returns:
            None，函数执行后的结果。
        """
        engine = AgentEngine(llm_gateway=mock_llm)
        messages = engine._build_initial_messages("test task")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "代码审查" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "test task"
