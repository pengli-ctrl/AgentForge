"""代码审查流水线集成测试 — 完整工作流端到端测试。

测试内容：
- Mock LLM + 事件总线 + 工作流引擎的完整流水线
- 事件驱动的 Agent 间通信
- Context Snapshot 隔离
- 动态路由决策
"""

from __future__ import annotations

import asyncio
import os

import pytest

from agentforge.agents.code_review_agent import CodeReviewAgent
from agentforge.agents.doc_generator_agent import DocGeneratorAgent
from agentforge.agents.security_scan_agent import SecurityScanAgent
from agentforge.agents.test_execution_agent import TestExecutionAgent
from agentforge.core.context_snapshot import ContextSnapshotManager
from agentforge.core.event_bus import EventBus
from agentforge.core.event_types import AgentEvent, EventType
from agentforge.llm.gateway import LLMResponse
from agentforge.workflow.engine import WorkflowEngine
from agentforge.workflow.registry import AgentRegistry
from tests.conftest import MockLLMGateway


@pytest.mark.asyncio
async def test_code_review_agent_execution() -> None:
    """代码审查 Agent 单独执行。"""
    llm = MockLLMGateway(
        [
            LLMResponse(
                content='{"review_items": [], "summary": "No issues found", "severity": "info"}',
                model="mock-model",
                usage={"prompt_tokens": 100, "completion_tokens": 50},
            )
        ]
    )

    agent = CodeReviewAgent(llm_gateway=llm)

    event = AgentEvent(
        event_type=EventType.TASK_SUBMITTED,
        source_agent="test",
        payload={"task": "Review code"},
        correlation_id="integration-001",
        context_snapshot={
            "code_content": "def add(a, b): return a + b",
            "review_config": {"types": ["security", "logic", "style"]},
        },
    )

    result_event = await agent.execute(event)

    assert result_event.event_type == EventType.AGENT_COMPLETED
    assert result_event.source_agent == "code-review"
    assert result_event.correlation_id == "integration-001"
    assert "code_review_result" in result_event.context_snapshot


@pytest.mark.asyncio
async def test_security_scan_agent_execution() -> None:
    """安全扫描 Agent 单独执行。"""
    llm = MockLLMGateway(
        [
            LLMResponse(
                content='{"findings": [], "severity": "info", "has_vulnerabilities": false}',
                model="mock-model",
            )
        ]
    )

    agent = SecurityScanAgent(llm_gateway=llm)

    event = AgentEvent(
        event_type=EventType.TASK_SUBMITTED,
        source_agent="test",
        payload={"task": "Scan for vulnerabilities"},
        correlation_id="integration-002",
        context_snapshot={
            "code_content": "def add(a, b): return a + b",
            "security_config": {"scan_types": ["sql_injection", "xss"]},
        },
    )

    result_event = await agent.execute(event)

    assert result_event.event_type == EventType.AGENT_COMPLETED
    assert result_event.source_agent == "security-scan"
    assert "security_scan_result" in result_event.context_snapshot


@pytest.mark.asyncio
async def test_event_bus_agent_communication() -> None:
    """事件总线驱动的 Agent 间通信。"""
    bus = EventBus(backend="memory")
    await bus.start()

    llm = MockLLMGateway(
        [
            LLMResponse(content="Review complete", model="mock-model"),
            LLMResponse(content="Test complete", model="mock-model"),
        ]
    )

    code_review = CodeReviewAgent(llm_gateway=llm)

    received_events: list[AgentEvent] = []

    async def capture_event(event: AgentEvent) -> None:
        """执行 capture_event 对应的逻辑，并返回处理结果。

        Args:
            event: AgentEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        received_events.append(event)

    # code_review 执行后把结果事件发回总线
    async def code_review_handler(event: AgentEvent) -> None:
        """执行 code_review_handler 对应的逻辑，并返回处理结果。

        Args:
            event: AgentEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        result = await code_review.execute(event)
        await bus.publish(result)

    bus.subscribe(EventType.TASK_SUBMITTED, code_review_handler)
    bus.subscribe(EventType.AGENT_COMPLETED, capture_event)

    # 发布任务事件
    task_event = AgentEvent(
        event_type=EventType.TASK_SUBMITTED,
        source_agent="api-gateway",
        payload={"task": "Review PR #42"},
        correlation_id="integration-003",
        context_snapshot={
            "code_content": "def add(a, b): return a + b",
            "review_config": {"types": ["security"]},
        },
    )

    await bus.publish(task_event)
    await asyncio.sleep(0.2)

    # code_review 应该执行并发布 AGENT_COMPLETED 事件
    assert len(received_events) >= 1
    assert received_events[0].source_agent == "code-review"

    await bus.stop()


@pytest.mark.asyncio
async def test_workflow_engine_full_pipeline() -> None:
    """工作流引擎完整流水线 — 多 Agent 串联执行。"""
    config_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "configs",
        "workflows",
    )

    # 使用 Mock LLM
    llm = MockLLMGateway(
        [
            LLMResponse(
                content='{"severity": "info", "summary": "Clean code"}',
                model="mock-model",
            ),
            LLMResponse(
                content='{"pass_rate": 0.95, "summary": "All tests passed"}',
                model="mock-model",
            ),
            LLMResponse(
                content="Documentation generated successfully.",
                model="mock-model",
            ),
        ]
    )

    # 创建 Agent 并注册
    registry = AgentRegistry()
    registry.register("code-review", CodeReviewAgent(llm_gateway=llm))
    registry.register("test-execution", TestExecutionAgent(llm_gateway=llm))
    registry.register("doc-generator", DocGeneratorAgent(llm_gateway=llm))

    # 创建工作流引擎
    engine = WorkflowEngine(registry=registry, config_dir=config_dir)
    engine.load("code-review-pipeline")

    # 执行工作流
    result = await engine.execute(
        workflow_name="code-review-pipeline",
        correlation_id="integration-004",
        input_data={
            "code_content": "def add(a, b): return a + b",
            "review_config": {"types": ["security", "logic"]},
            "code_path": "/test/code.py",
            "test_config": {"framework": "pytest"},
            "task": "Review test code",
        },
    )

    # 工作流应执行多个 Agent
    assert len(result) >= 2
    assert "code-review" in result

    engine.registry.clear()


@pytest.mark.asyncio
async def test_context_snapshot_isolation_in_pipeline() -> None:
    """Context Snapshot 隔离 — Agent 只看到自己需要的上下文。"""
    manager = ContextSnapshotManager()

    # 创建初始上下文
    context = {
        "code_content": "def add(a, b): return a + b",
        "review_config": {"types": ["security"]},
        "code_path": "/test/code.py",
        "test_config": {"framework": "pytest"},
    }

    snapshot = manager.create_snapshot("isolation-test", context)

    # CodeReviewAgent 只提取 code_content 和 review_config
    llm = MockLLMGateway()
    code_review = CodeReviewAgent(llm_gateway=llm)
    extracted = code_review._extract_context(snapshot.to_dict())

    assert "code_content" in extracted
    assert "review_config" in extracted
    assert "code_path" not in extracted  # 不需要的数据不应出现
    assert "test_config" not in extracted

    # TestExecutionAgent 只提取 code_path 和 test_config
    test_agent = TestExecutionAgent(llm_gateway=llm)
    extracted = test_agent._extract_context(snapshot.to_dict())

    assert "code_path" in extracted
    assert "test_config" in extracted
    assert "code_content" not in extracted  # 不需要的数据不应出现
    assert "review_config" not in extracted

    manager.cleanup("isolation-test")
