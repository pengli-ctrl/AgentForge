"""Agent ReAct 循环单元测试 — 多轮推理 + 工具调用。

测试要点：
- 单轮 ReAct（LLM 直接给出答案，不调工具）
- 多轮 ReAct（LLM 先调工具，再给出答案）
- max_iterations 终止
- token 预算终止
- 工具结果作为 observation 累积到 messages
"""

from __future__ import annotations

from typing import Any

import pytest

from agentforge.core.agent import Agent
from agentforge.core.base_tool import BaseTool, ToolRegistry, ToolResult
from agentforge.core.event_types import AgentEvent, EventType
from agentforge.llm.gateway import LLMGateway, LLMResponse, ToolCall
from tests.conftest import MockLLMGateway

# ──────────────────────────────────────────────────────────────────────────
# 测试用 Agent 和 Tool
# ──────────────────────────────────────────────────────────────────────────


class SimpleAgent(Agent):
    """简单的测试用 Agent — 用于 ReAct 循环测试。"""

    def __init__(self, llm_gateway, tool_registry=None, max_iterations=5, token_budget=8000):
        super().__init__(
            llm_gateway=llm_gateway,
            name="simple-agent",
            tool_registry=tool_registry,
            max_iterations=max_iterations,
            token_budget=token_budget,
        )
        self.prompt_template = "Task: {task}\nContext: {context}"

    def _extract_context(self, context_snapshot: dict[str, Any]) -> dict[str, Any]:
        return context_snapshot

    def _build_initial_messages(self, task: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": task},
        ]


class EchoTool(BaseTool):
    """简单的回显工具 — 用于测试 ReAct 工具调用。"""

    @property
    def name(self) -> str:
        return "echo"

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo back the input",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to echo"},
                    },
                    "required": ["text"],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        text = kwargs.get("text", "")
        return ToolResult(success=True, output=f"Echo: {text}")


# ──────────────────────────────────────────────────────────────────────────
# 单轮 ReAct 测试
# ──────────────────────────────────────────────────────────────────────────


class TestReActSingleIteration:
    """单轮 ReAct 循环测试 — LLM 直接给出答案。"""

    @pytest.mark.asyncio
    async def test_single_iteration_no_tool_calls(self) -> None:
        """LLM 返回无 tool_calls → 循环立即终止。"""
        llm = MockLLMGateway(
            [
                LLMResponse(content="Final answer", model="mock"),
            ]
        )
        agent = SimpleAgent(llm_gateway=llm, max_iterations=5)

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "Say hello"},
            correlation_id="react-001",
            context_snapshot={},
        )

        result = await agent.execute(event)

        assert result.event_type == EventType.AGENT_COMPLETED
        assert result.source_agent == "simple-agent"
        assert "Final answer" in result.payload["result"]
        assert llm.call_count == 1  # 只调用了 1 次 LLM

    @pytest.mark.asyncio
    async def test_empty_response(self) -> None:
        """LLM 返回空响应 → 正常终止。"""
        llm = MockLLMGateway(
            [
                LLMResponse(content="", model="mock"),
            ]
        )
        agent = SimpleAgent(llm_gateway=llm)

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "test"},
            correlation_id="react-002",
            context_snapshot={},
        )

        result = await agent.execute(event)
        assert result.event_type == EventType.AGENT_COMPLETED
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_no_prompt_template(self) -> None:
        """prompt_template 为空时优雅处理。"""
        llm = MockLLMGateway(
            [
                LLMResponse(content="ok", model="mock"),
            ]
        )
        agent = SimpleAgent(llm_gateway=llm)
        agent.prompt_template = ""  # 清空 prompt_template

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "test task"},
            correlation_id="react-003",
            context_snapshot={},
        )

        result = await agent.execute(event)
        assert result.event_type == EventType.AGENT_COMPLETED
        assert llm.call_count == 1


# ──────────────────────────────────────────────────────────────────────────
# 多轮 ReAct 测试
# ──────────────────────────────────────────────────────────────────────────


class TestReActMultipleIterations:
    """多轮 ReAct 循环测试 — LLM 先调工具，再给出答案。"""

    @pytest.mark.asyncio
    async def test_two_iterations_with_tool_call(self) -> None:
        """LLM 第一轮调工具，第二轮给出答案。"""
        llm = MockLLMGateway(
            [
                # 第一轮：LLM 请求调用工具
                LLMResponse(
                    content="Let me check...",
                    tool_calls=[ToolCall(name="echo", arguments={"text": "hello"})],
                    has_tool_calls=True,
                    model="mock",
                    usage={"total_tokens": 100},
                ),
                # 第二轮：LLM 给出最终答案
                LLMResponse(
                    content="The echo result is: Echo: hello",
                    model="mock",
                    usage={"total_tokens": 80},
                ),
            ]
        )

        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = SimpleAgent(llm_gateway=llm, tool_registry=registry, max_iterations=5)

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "Echo hello"},
            correlation_id="react-004",
            context_snapshot={},
        )

        result = await agent.execute(event)

        assert result.event_type == EventType.AGENT_COMPLETED
        assert "Echo: hello" in result.payload["result"]
        assert llm.call_count == 2  # 两轮 LLM 调用

    @pytest.mark.asyncio
    async def test_three_iterations_with_tool_calls(self) -> None:
        """LLM 连续调用两次工具，第三轮给出答案。"""
        llm = MockLLMGateway(
            [
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(name="echo", arguments={"text": "first"})],
                    has_tool_calls=True,
                    model="mock",
                    usage={"total_tokens": 50},
                ),
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(name="echo", arguments={"text": "second"})],
                    has_tool_calls=True,
                    model="mock",
                    usage={"total_tokens": 50},
                ),
                LLMResponse(
                    content="Done: first and second",
                    model="mock",
                    usage={"total_tokens": 50},
                ),
            ]
        )

        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = SimpleAgent(llm_gateway=llm, tool_registry=registry, max_iterations=5)

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "Echo twice"},
            correlation_id="react-005",
            context_snapshot={},
        )

        result = await agent.execute(event)

        assert result.event_type == EventType.AGENT_COMPLETED
        assert "first and second" in result.payload["result"]
        assert llm.call_count == 3

    @pytest.mark.asyncio
    async def test_tool_result_in_messages(self) -> None:
        """验证工具结果作为 observation 累积到 messages。"""
        received_messages: list[Any] = []

        class CapturingGateway(LLMGateway):
            def __init__(self):
                super().__init__(model="capture")
                self._responses = [
                    LLMResponse(
                        content="",
                        tool_calls=[ToolCall(name="echo", arguments={"text": "check"})],
                        has_tool_calls=True,
                        model="capture",
                        usage={"total_tokens": 50},
                    ),
                    LLMResponse(content="final", model="capture", usage={"total_tokens": 30}),
                ]
                self._idx = 0

            async def chat(self, messages, tools=None, max_tokens=None, temperature=None):
                # 深拷贝 messages，因为 ReAct 循环会原地修改同一个列表
                import copy

                received_messages.append(copy.deepcopy(messages))
                resp = self._responses[self._idx]
                self._idx += 1
                return resp

        llm = CapturingGateway()
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = SimpleAgent(llm_gateway=llm, tool_registry=registry, max_iterations=5)

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "test"},
            correlation_id="react-006",
            context_snapshot={},
        )

        await agent.execute(event)

        # 第一次调用：只有 system + user
        assert len(received_messages[0]) == 2
        assert received_messages[0][0]["role"] == "system"
        assert received_messages[0][1]["role"] == "user"

        # 第二次调用：system + user + assistant + tool observation
        assert len(received_messages[1]) == 4
        assert received_messages[1][2]["role"] == "assistant"
        assert received_messages[1][3]["role"] == "user"
        assert "Echo: check" in received_messages[1][3]["content"]


# ──────────────────────────────────────────────────────────────────────────
# 终止条件测试
# ──────────────────────────────────────────────────────────────────────────


class TestReActTermination:
    """ReAct 循环终止条件测试。"""

    @pytest.mark.asyncio
    async def test_max_iterations_termination(self) -> None:
        """LLM 持续返回 tool_calls → 达到 max_iterations 终止。"""
        llm = MockLLMGateway(
            [
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(name="echo", arguments={"text": f"iter-{i}"})],
                    has_tool_calls=True,
                    model="mock",
                    usage={"total_tokens": 10},
                )
                for i in range(10)  # 足够多的响应
            ]
        )

        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = SimpleAgent(llm_gateway=llm, tool_registry=registry, max_iterations=3)

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "loop"},
            correlation_id="react-007",
            context_snapshot={},
        )

        result = await agent.execute(event)

        assert result.event_type == EventType.AGENT_COMPLETED
        assert llm.call_count == 3  # 恰好 3 次（max_iterations）

    @pytest.mark.asyncio
    async def test_token_budget_termination(self) -> None:
        """累计 token 接近预算 → 强制终止循环。"""
        llm = MockLLMGateway(
            [
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(name="echo", arguments={"text": "x"})],
                    has_tool_calls=True,
                    model="mock",
                    usage={"total_tokens": 500},  # 每次消耗 500 token
                )
                for _ in range(10)
            ]
        )

        registry = ToolRegistry()
        registry.register(EchoTool())
        # token_budget=1000，每次消耗 500，第二次迭代时累计 500 < 1000，
        # 第三次迭代时累计 1000 >= 1000 → 终止
        agent = SimpleAgent(
            llm_gateway=llm,
            tool_registry=registry,
            max_iterations=10,
            token_budget=1000,
        )

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "budget test"},
            correlation_id="react-008",
            context_snapshot={},
        )

        result = await agent.execute(event)

        assert result.event_type == EventType.AGENT_COMPLETED
        # 第一次迭代：tokens=0 < 1000 → 调用 LLM → tokens=500
        # 第二次迭代：tokens=500 < 1000 → 调用 LLM → tokens=1000
        # 第三次迭代：tokens=1000 >= 1000 → 终止
        assert llm.call_count == 2

    @pytest.mark.asyncio
    async def test_max_iterations_one(self) -> None:
        """max_iterations=1 → 只执行一轮。"""
        llm = MockLLMGateway(
            [
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(name="echo", arguments={"text": "x"})],
                    has_tool_calls=True,
                    model="mock",
                    usage={"total_tokens": 10},
                ),
                LLMResponse(content="should not reach", model="mock"),
            ]
        )

        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = SimpleAgent(llm_gateway=llm, tool_registry=registry, max_iterations=1)

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "one shot"},
            correlation_id="react-009",
            context_snapshot={},
        )

        await agent.execute(event)
        assert llm.call_count == 1


# ──────────────────────────────────────────────────────────────────────────
# 与现有 Agent 子类兼容性测试
# ──────────────────────────────────────────────────────────────────────────


class TestReActWithExistingAgents:
    """ReAct 循环与现有 Agent 子类的兼容性测试。"""

    @pytest.mark.asyncio
    async def test_code_review_agent_react(self) -> None:
        """CodeReviewAgent 在 ReAct 模式下正常工作。"""
        from agentforge.agents.code_review_agent import CodeReviewAgent

        llm = MockLLMGateway(
            [
                LLMResponse(
                    content='{"review_items": [], "summary": "No issues", "severity": "info"}',
                    model="mock",
                    usage={"total_tokens": 100},
                ),
            ]
        )

        agent = CodeReviewAgent(llm_gateway=llm)

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "Review code"},
            correlation_id="react-010",
            context_snapshot={
                "code_content": "def add(a, b): return a + b",
                "review_config": {"types": ["security"]},
            },
        )

        result = await agent.execute(event)
        assert result.event_type == EventType.AGENT_COMPLETED
        assert result.source_agent == "code-review"
        assert "code_review_result" in result.context_snapshot
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_test_execution_agent_react(self) -> None:
        """TestExecutionAgent 在 ReAct 模式下正常工作。"""
        from agentforge.agents.test_execution_agent import TestExecutionAgent

        llm = MockLLMGateway(
            [
                LLMResponse(
                    content='{"pass_rate": 0.95, "summary": "All passed"}',
                    model="mock",
                    usage={"total_tokens": 80},
                ),
            ]
        )

        agent = TestExecutionAgent(llm_gateway=llm)

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "Run tests"},
            correlation_id="react-011",
            context_snapshot={
                "code_path": "/test/code.py",
                "test_config": {"framework": "pytest"},
            },
        )

        result = await agent.execute(event)
        assert result.event_type == EventType.AGENT_COMPLETED
        assert result.source_agent == "test-execution"
        assert "test_result" in result.context_snapshot
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_deploy_agent_react(self) -> None:
        """DeployAgent 在 ReAct 模式下正常工作（含前置条件校验）。"""
        from agentforge.agents.deploy_agent import DeployAgent

        llm = MockLLMGateway(
            [
                LLMResponse(
                    content='{"status": "success", "summary": "Deployed"}',
                    model="mock",
                    usage={"total_tokens": 50},
                ),
            ]
        )

        agent = DeployAgent(llm_gateway=llm)

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "Deploy"},
            correlation_id="react-012",
            context_snapshot={
                "deploy_config": {"target": "staging"},
                "test_result": {"pass_rate": 0.95},
                "security_scan_result": {"severity": "info"},
            },
        )

        result = await agent.execute(event)
        assert result.event_type == EventType.AGENT_COMPLETED
        assert result.source_agent == "deploy"
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_deploy_agent_blocked_by_preconditions(self) -> None:
        """DeployAgent 前置条件不满足时返回 AGENT_FAILED。"""
        from agentforge.agents.deploy_agent import DeployAgent

        llm = MockLLMGateway()
        agent = DeployAgent(llm_gateway=llm)

        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            payload={"task": "Deploy"},
            correlation_id="react-013",
            context_snapshot={
                "deploy_config": {"target": "staging"},
                "test_result": {"pass_rate": 0.5},  # 低于阈值
                "security_scan_result": {"severity": "info"},
            },
        )

        result = await agent.execute(event)
        assert result.event_type == EventType.AGENT_FAILED
        assert llm.call_count == 0  # 前置条件不满足，不调用 LLM
