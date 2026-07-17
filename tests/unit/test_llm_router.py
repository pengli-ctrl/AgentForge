"""LLMRouter 单元测试 — LLM 驱动的工作流路由决策。

测试要点：路由决策、JSON 解析、降级处理、单 Agent 自动路由。
"""

from __future__ import annotations

import json

import pytest

from agentforge.llm.gateway import LLMResponse
from agentforge.workflow.llm_router import ROUTER_PROMPT, LLMRouter, RouteDecision
from tests.conftest import MockLLMGateway


class TestRouterInit:
    """初始化测试。"""

    def test_default_agent(self) -> None:
        llm = MockLLMGateway()
        router = LLMRouter(llm_gateway=llm)
        assert router.default_agent == "code-review"

    def test_custom_default_agent(self) -> None:
        llm = MockLLMGateway()
        router = LLMRouter(llm_gateway=llm, default_agent="security-scan")
        assert router.default_agent == "security-scan"

    def test_prompt_template_exists(self) -> None:
        """ROUTER_PROMPT 应包含必要占位符。"""
        assert "{task}" in ROUTER_PROMPT
        assert "{agent_outputs}" in ROUTER_PROMPT
        assert "{available_agents}" in ROUTER_PROMPT
        assert "agent_name" in ROUTER_PROMPT
        assert "reason" in ROUTER_PROMPT


class TestRouteDecision:
    """RouteDecision 数据类测试。"""

    def test_create_decision(self) -> None:
        decision = RouteDecision(agent_name="security-scan", reason="critical issue")
        assert decision.agent_name == "security-scan"
        assert decision.reason == "critical issue"

    def test_to_dict(self) -> None:
        decision = RouteDecision(agent_name="test-execution", reason="tests needed")
        d = decision.to_dict()
        assert d["agent_name"] == "test-execution"
        assert d["reason"] == "tests needed"


class TestRoute:
    """route 方法测试。"""

    @pytest.mark.asyncio
    async def test_route_returns_dict_with_agent_and_reason(self) -> None:
        """route 应返回包含 agent_name 和 reason 的字典。"""
        response = json.dumps(
            {
                "agent_name": "security-scan",
                "reason": "Code review found SQL injection vulnerability",
            }
        )
        llm = MockLLMGateway(responses=[LLMResponse(content=response)])
        router = LLMRouter(llm_gateway=llm)

        result = await router.route(
            task="Review code for security issues",
            agent_outputs={"code-review": {"severity": "critical"}},
            available_agents=["security-scan", "test-execution"],
        )

        assert result["agent_name"] == "security-scan"
        assert "SQL injection" in result["reason"]

    @pytest.mark.asyncio
    async def test_route_calls_llm_once(self) -> None:
        """route 应只调用 LLM 一次。"""
        response = json.dumps({"agent_name": "test-execution", "reason": "need tests"})
        llm = MockLLMGateway(responses=[LLMResponse(content=response)])
        router = LLMRouter(llm_gateway=llm)

        await router.route(
            task="test",
            agent_outputs={},
            available_agents=["test-execution", "security-scan"],
        )
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_route_empty_available_agents_uses_default(self) -> None:
        """没有可选 Agent 时使用 default_agent。"""
        llm = MockLLMGateway()
        router = LLMRouter(llm_gateway=llm, default_agent="code-review")

        result = await router.route("task", {}, [])
        assert result["agent_name"] == "code-review"
        assert "no agents" in result["reason"]

    @pytest.mark.asyncio
    async def test_route_single_agent_auto_route(self) -> None:
        """只有一个可选 Agent 时自动路由，不调用 LLM。"""
        llm = MockLLMGateway()
        router = LLMRouter(llm_gateway=llm)

        result = await router.route(
            "task",
            {},
            ["security-scan"],
        )
        assert result["agent_name"] == "security-scan"
        assert "only available" in result["reason"]
        assert llm.call_count == 0  # 不应调用 LLM

    @pytest.mark.asyncio
    async def test_route_invalid_agent_uses_default(self) -> None:
        """LLM 返回不存在的 Agent 名称时应使用 default_agent。"""
        response = json.dumps(
            {
                "agent_name": "non-existent-agent",
                "reason": "reason",
            }
        )
        llm = MockLLMGateway(responses=[LLMResponse(content=response)])
        router = LLMRouter(llm_gateway=llm, default_agent="code-review")

        result = await router.route(
            "task",
            {},
            ["security-scan", "test-execution"],
        )
        assert result["agent_name"] == "code-review"
        assert "invalid_agent" in result["reason"]

    @pytest.mark.asyncio
    async def test_route_invalid_json_falls_back(self) -> None:
        """LLM 返回无效 JSON 时应降级为 default_agent。"""
        llm = MockLLMGateway(responses=[LLMResponse(content="This is not JSON")])
        router = LLMRouter(llm_gateway=llm, default_agent="code-review")

        result = await router.route(
            "task",
            {},
            ["security-scan", "test-execution"],
        )
        assert result["agent_name"] == "code-review"
        assert "parse_error" in result["reason"]

    @pytest.mark.asyncio
    async def test_route_markdown_wrapped_json(self) -> None:
        """LLM 返回 markdown 包裹的 JSON 时应正确解析。"""
        response = (
            "```json\n"
            + json.dumps(
                {
                    "agent_name": "security-scan",
                    "reason": "found vulnerability",
                }
            )
            + "\n```"
        )
        llm = MockLLMGateway(responses=[LLMResponse(content=response)])
        router = LLMRouter(llm_gateway=llm)

        result = await router.route(
            "task",
            {},
            ["security-scan", "test-execution"],
        )
        assert result["agent_name"] == "security-scan"
        assert "found vulnerability" in result["reason"]

    @pytest.mark.asyncio
    async def test_route_preserves_agent_outputs_in_prompt(self) -> None:
        """route 应在 prompt 中包含已完成的 Agent 输出。"""
        captured_messages: list = []

        class _CapturingLLM(MockLLMGateway):
            async def chat(self, messages, tools=None, max_tokens=None, temperature=None):
                captured_messages.extend(messages)
                return LLMResponse(
                    content=json.dumps(
                        {
                            "agent_name": "security-scan",
                            "reason": "test",
                        }
                    )
                )

        llm = _CapturingLLM()
        router = LLMRouter(llm_gateway=llm)

        await router.route(
            task="Review code",
            agent_outputs={
                "code-review": {"severity": "high", "issues": ["sql injection"]},
            },
            available_agents=["security-scan", "test-execution"],
        )

        # 验证 prompt 包含已完成的 Agent 输出
        user_msg = captured_messages[1]["content"]
        assert "code-review" in user_msg
        assert "sql injection" in user_msg

    @pytest.mark.asyncio
    async def test_route_long_output_truncated(self) -> None:
        """过长的 Agent 输出应被截断。"""
        long_output = "x" * 1000

        response = json.dumps({"agent_name": "security-scan", "reason": "test"})
        llm = MockLLMGateway(responses=[LLMResponse(content=response)])
        router = LLMRouter(llm_gateway=llm)

        # 不应报错
        result = await router.route(
            "task",
            {"agent-1": long_output},
            ["security-scan", "test-execution"],
        )
        assert result["agent_name"] == "security-scan"


class TestParseRoute:
    """_parse_route 方法测试。"""

    def test_parse_valid_json(self) -> None:
        llm = MockLLMGateway()
        router = LLMRouter(llm_gateway=llm)
        content = json.dumps({"agent_name": "test-execution", "reason": "need tests"})

        decision = router._parse_route(content, ["test-execution", "security-scan"])
        assert decision.agent_name == "test-execution"
        assert decision.reason == "need tests"

    def test_parse_missing_reason(self) -> None:
        llm = MockLLMGateway()
        router = LLMRouter(llm_gateway=llm)
        content = json.dumps({"agent_name": "test-execution"})

        decision = router._parse_route(content, ["test-execution"])
        assert decision.agent_name == "test-execution"
        assert decision.reason == ""

    def test_parse_no_json_returns_default(self) -> None:
        llm = MockLLMGateway()
        router = LLMRouter(llm_gateway=llm, default_agent="code-review")

        decision = router._parse_route("not json at all", ["code-review"])
        assert decision.agent_name == "code-review"
        assert "parse_error" in decision.reason
