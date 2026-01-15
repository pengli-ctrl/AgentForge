"""事件总线测试 — publish/subscribe/异常隔离。

测试内容：
- 发布事件到无订阅者时不报错
- 发布事件到单个订阅者
- 发布事件到多个订阅者（并发分发）
- 单个订阅者异常不影响其他订阅者（异常隔离）
- 事件携带 correlation_id 和 context_snapshot
"""

from __future__ import annotations

import asyncio

import pytest

from agentforge.core.event_bus import EventBus
from agentforge.core.event_types import AgentEvent, EventType


@pytest.mark.asyncio
async def test_publish_no_subscribers() -> None:
    """发布事件到无订阅者时不报错。"""
    bus = EventBus(backend="memory")
    await bus.start()

    event = AgentEvent(
        event_type=EventType.TASK_SUBMITTED,
        source_agent="test",
        payload={"task": "test"},
        correlation_id="test-001",
    )

    # 不应该抛出异常
    await bus.publish(event)
    await bus.stop()


@pytest.mark.asyncio
async def test_publish_to_single_subscriber() -> None:
    """发布事件到单个订阅者。"""
    bus = EventBus(backend="memory")
    await bus.start()

    received: list[AgentEvent] = []

    async def callback(event: AgentEvent) -> None:
        """执行 callback 对应的逻辑，并返回处理结果。

        Args:
            event: AgentEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        received.append(event)

    bus.subscribe(EventType.TASK_SUBMITTED, callback)

    event = AgentEvent(
        event_type=EventType.TASK_SUBMITTED,
        source_agent="test",
        payload={"task": "test"},
        correlation_id="test-002",
    )

    await bus.publish(event)
    await asyncio.sleep(0.1)  # 等待异步处理

    assert len(received) == 1
    assert received[0].correlation_id == "test-002"
    assert received[0].payload["task"] == "test"

    await bus.stop()


@pytest.mark.asyncio
async def test_publish_to_multiple_subscribers() -> None:
    """发布事件到多个订阅者（并发分发）。"""
    bus = EventBus(backend="memory")
    await bus.start()

    received_1: list[AgentEvent] = []
    received_2: list[AgentEvent] = []

    async def callback_1(event: AgentEvent) -> None:
        """执行 callback_1 对应的逻辑，并返回处理结果。

        Args:
            event: AgentEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        received_1.append(event)

    async def callback_2(event: AgentEvent) -> None:
        """执行 callback_2 对应的逻辑，并返回处理结果。

        Args:
            event: AgentEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        received_2.append(event)

    bus.subscribe(EventType.AGENT_COMPLETED, callback_1)
    bus.subscribe(EventType.AGENT_COMPLETED, callback_2)

    event = AgentEvent(
        event_type=EventType.AGENT_COMPLETED,
        source_agent="agent-1",
        payload={"result": "done"},
        correlation_id="test-003",
    )

    await bus.publish(event)
    await asyncio.sleep(0.1)

    assert len(received_1) == 1
    assert len(received_2) == 1
    assert received_1[0].correlation_id == "test-003"
    assert received_2[0].correlation_id == "test-003"

    await bus.stop()


@pytest.mark.asyncio
async def test_subscriber_exception_isolation() -> None:
    """单个订阅者异常不影响其他订阅者（异常隔离）。"""
    bus = EventBus(backend="memory")
    await bus.start()

    received: list[AgentEvent] = []

    async def failing_callback(event: AgentEvent) -> None:
        """执行 failing_callback 对应的逻辑，并返回处理结果。

        Args:
            event: AgentEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        raise RuntimeError("Intentional test failure")

    async def healthy_callback(event: AgentEvent) -> None:
        """执行 healthy_callback 对应的逻辑，并返回处理结果。

        Args:
            event: AgentEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        received.append(event)

    bus.subscribe(EventType.TASK_FAILED, failing_callback)
    bus.subscribe(EventType.TASK_FAILED, healthy_callback)

    event = AgentEvent(
        event_type=EventType.TASK_FAILED,
        source_agent="test",
        payload={"error": "test"},
        correlation_id="test-004",
    )

    # 不应该抛出异常
    await bus.publish(event)
    await asyncio.sleep(0.1)

    # 健康的订阅者应该正常收到事件
    assert len(received) == 1

    await bus.stop()


@pytest.mark.asyncio
async def test_event_carries_correlation_id_and_snapshot() -> None:
    """验证 event_carries_correlation_id_and_snapshot 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    bus = EventBus(backend="memory")
    await bus.start()

    received: list[AgentEvent] = []

    async def callback(event: AgentEvent) -> None:
        """执行 callback 对应的逻辑，并返回处理结果。

        Args:
            event: AgentEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        received.append(event)

    bus.subscribe(EventType.TASK_SUBMITTED, callback)

    snapshot = {"code": "print('hello')", "config": {"strict": True}}
    event = AgentEvent(
        event_type=EventType.TASK_SUBMITTED,
        source_agent="api-gateway",
        payload={"task": "review"},
        correlation_id="trace-001",
        context_snapshot=snapshot,
    )

    await bus.publish(event)
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0].correlation_id == "trace-001"
    assert received[0].context_snapshot == snapshot

    await bus.stop()


@pytest.mark.asyncio
async def test_subscribe_different_event_types() -> None:
    """不同事件类型的订阅者互不干扰。"""
    bus = EventBus(backend="memory")
    await bus.start()

    submitted_received: list[AgentEvent] = []
    completed_received: list[AgentEvent] = []

    async def on_submitted(event: AgentEvent) -> None:
        """执行 on_submitted 对应的逻辑，并返回处理结果。

        Args:
            event: AgentEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        submitted_received.append(event)

    async def on_completed(event: AgentEvent) -> None:
        """执行 on_completed 对应的逻辑，并返回处理结果。

        Args:
            event: AgentEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        completed_received.append(event)

    bus.subscribe(EventType.TASK_SUBMITTED, on_submitted)
    bus.subscribe(EventType.AGENT_COMPLETED, on_completed)

    await bus.publish(
        AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="test",
            correlation_id="test-005",
        )
    )
    await bus.publish(
        AgentEvent(
            event_type=EventType.AGENT_COMPLETED,
            source_agent="test",
            correlation_id="test-006",
        )
    )
    await asyncio.sleep(0.1)

    assert len(submitted_received) == 1
    assert len(completed_received) == 1
    assert submitted_received[0].correlation_id == "test-005"
    assert completed_received[0].correlation_id == "test-006"

    await bus.stop()
