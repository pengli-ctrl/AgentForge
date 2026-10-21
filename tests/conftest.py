"""共享测试夹具测试模块。

提供测试中常用的 fixture，避免每个测试文件重复定义 Mock 对象。

Mock 策略（来自博客文章的测试策略）：
- LLM 用固定响应的 Mock（确定性 Mock，用于单元测试）
- 工具用 Stub
- EventBus 用内存后端
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentforge.core.context_snapshot import ContextSnapshotManager
from agentforge.core.event_bus import EventBus
from agentforge.core.event_types import AgentEvent, EventType
from agentforge.llm.gateway import LLMGateway, LLMResponse


class MockLLMGateway(LLMGateway):
    """Mock LLM Gateway — 返回预设响应。

    用于单元测试，提供确定性的 LLM 响应。
    支持脚本化响应链（按顺序返回预设响应）。
    """

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        """初始化模拟LLM 网关。

        Args:
            responses: 响应。
        """
        super().__init__(model="mock-model")
        self._responses = responses or []
        self._index = 0
        self.call_count = 0

    async def chat(
        self,
        messages: list[dict[str, str]] | str,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """发送模拟LLM 网关。

        Args:
            messages: 消息列表。
            tools: 可供模型调用的工具定义。
            max_tokens: 生成结果允许使用的最大 Token 数。
            temperature: 模型采样温度。

        Returns:
            处理结果对象。
        """
        self.call_count += 1

        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp

        # 默认响应
        return LLMResponse(
            content="Mock LLM response.",
            model="mock-model",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )


class ScriptedLLMGateway(LLMGateway):
    """脚本化 LLM Gateway — 按预设脚本返回响应。

    用于集成测试，模拟 Agent 间的反馈环。
    """

    def __init__(self, scripts: dict[str, list[str]]) -> None:
        """初始化脚本化LLM 网关。

        Args:
            scripts: 输入参数。
        """
        super().__init__(model="scripted-model")
        self._scripts = scripts
        self._indices: dict[str, int] = {}

    async def chat(
        self,
        messages: list[dict[str, str]] | str,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        # 尝试从消息中推断 Agent 名称
        """发送脚本化LLM 网关。

        Args:
            messages: 消息列表。
            tools: 可供模型调用的工具定义。
            max_tokens: 生成结果允许使用的最大 Token 数。
            temperature: 模型采样温度。

        Returns:
            处理结果对象。
        """
        agent_name = "default"
        if isinstance(messages, list) and messages:
            system_msg = messages[0].get("content", "")
            for name in self._scripts:
                if name in system_msg.lower():
                    agent_name = name
                    break

        idx = self._indices.get(agent_name, 0)
        scripts = self._scripts.get(agent_name, ["Default response."])

        content = scripts[idx] if idx < len(scripts) else scripts[-1]
        self._indices[agent_name] = idx + 1

        return LLMResponse(
            content=content,
            model="scripted-model",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )


@pytest.fixture
def event_bus() -> EventBus:
    """提供内存后端的事件总线。

    Returns:
        事件结果。
    """
    return EventBus(backend="memory")


@pytest.fixture
def snapshot_manager() -> ContextSnapshotManager:
    """提供上下文快照管理器。

    Returns:
        上下文快照管理器结果。
    """
    return ContextSnapshotManager()


@pytest.fixture
def mock_llm() -> MockLLMGateway:
    """处理模拟LLM。

    Returns:
        模拟LLM 网关结果。
    """
    return MockLLMGateway()


@pytest.fixture
def scripted_llm() -> ScriptedLLMGateway:
    """提供脚本化 LLM Gateway。

    Returns:
        脚本化LLM 网关结果。
    """
    return ScriptedLLMGateway(
        scripts={
            "code-review": ["建议拆分函数降低复杂度"],
            "test-execution": ["测试失败：函数签名变化"],
        }
    )


@pytest.fixture
def sample_event() -> AgentEvent:
    """提供测试用的事件。

    Returns:
        智能体事件结果。
    """
    return AgentEvent(
        event_type=EventType.TASK_SUBMITTED,
        source_agent="test-source",
        payload={"task": "Review test code"},
        correlation_id="test-correlation-001",
        context_snapshot={
            "code_content": "def add(a, b): return a + b",
            "review_config": {"types": ["security", "logic", "style"]},
        },
    )


@pytest.fixture
def sample_context() -> dict[str, Any]:
    """提供测试用的上下文数据。

    Returns:
        结构化结果字典。
    """
    return {
        "code_content": "def add(a, b): return a + b",
        "review_config": {"types": ["security", "logic", "style"]},
        "code_path": "/test/code.py",
        "test_config": {"framework": "pytest"},
    }


@pytest.fixture
def event_loop():
    """提供事件循环。

    Yields:
        逐次生成的结果。
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
