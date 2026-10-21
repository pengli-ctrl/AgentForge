"""PulseShaper 单元测试 — 请求速率整形与突发限流。

测试要点：请求速率整形、突发限流、平滑输出。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from agentforge.core.event_types import AgentEvent, EventType
from agentforge.safety.pulse_shaper import PulseShaper


def _make_event(source: str = "test-agent", corr_id: str = "corr-1") -> AgentEvent:
    """构造事件。

    Args:
        source: 调用或事件来源。
        corr_id: 关联 ID。

    Returns:
        智能体事件结果。
    """
    return AgentEvent(
        event_type=EventType.AGENT_COMPLETED,
        source_agent=source,
        correlation_id=corr_id,
        payload={"data": "test"},
    )


class TestPulseShaperInit:
    """初始化测试。"""

    def test_default_values(self) -> None:
        """验证默认值对应的测试场景。"""
        ps = PulseShaper()
        assert ps.window == 5.0
        assert ps.max_batch == 10
        assert ps.pending == []
        assert ps.flush_task is None

    def test_custom_values(self) -> None:
        """验证自定义值对应的测试场景。"""
        ps = PulseShaper(window_seconds=2.0, max_batch_size=5)
        assert ps.window == 2.0
        assert ps.max_batch == 5


class TestBatchFlush:
    """验证测试批次刷新行为的测试集合。"""

    @pytest.mark.asyncio
    async def test_flush_on_batch_full(self) -> None:
        """验证刷新时批次完整对应的测试场景。"""
        ps = PulseShaper(window_seconds=10.0, max_batch_size=3)
        bus = AsyncMock()

        for i in range(3):
            await ps.on_event(_make_event(f"agent-{i}"), bus)

        bus.publish.assert_awaited_once()
        published_event = bus.publish.call_args[0][0]
        assert published_event.event_type == EventType.BATCH_EVENT
        assert published_event.payload["batch_size"] == 3
        assert ps.pending == []

    @pytest.mark.asyncio
    async def test_no_flush_below_batch_threshold(self) -> None:
        """验证无刷新以下批次阈值对应的测试场景。"""
        ps = PulseShaper(window_seconds=10.0, max_batch_size=5)
        bus = AsyncMock()

        await ps.on_event(_make_event(), bus)
        bus.publish.assert_not_awaited()
        assert len(ps.pending) == 1

    @pytest.mark.asyncio
    async def test_flush_creates_merged_event(self) -> None:
        """验证刷新创建事件对应的测试场景。"""
        ps = PulseShaper(window_seconds=10.0, max_batch_size=2)
        bus = AsyncMock()

        await ps.on_event(_make_event("agent-a", "corr-x"), bus)
        await ps.on_event(_make_event("agent-b", "corr-x"), bus)

        published = bus.publish.call_args[0][0]
        sub_events = published.payload["sub_events"]
        assert len(sub_events) == 2
        assert sub_events[0]["source"] == "agent-a"
        assert sub_events[1]["source"] == "agent-b"


class TestWindowTimeout:
    """验证测试窗口超时行为的测试集合。"""

    @pytest.mark.asyncio
    async def test_delayed_flush_after_window(self) -> None:
        """验证延迟刷新之后窗口对应的测试场景。"""
        ps = PulseShaper(window_seconds=0.05, max_batch_size=10)
        bus = AsyncMock()

        await ps.on_event(_make_event(), bus)
        assert ps.flush_task is not None

        await asyncio.sleep(0.1)
        bus.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flush_task_cleared_after_flush(self) -> None:
        """验证刷新任务之后刷新对应的测试场景。"""
        ps = PulseShaper(window_seconds=0.05, max_batch_size=10)
        bus = AsyncMock()

        await ps.on_event(_make_event(), bus)
        await asyncio.sleep(0.1)
        assert ps.flush_task is None


class TestFlushEmpty:
    """验证测试刷新空行为的测试集合。"""

    @pytest.mark.asyncio
    async def test_flush_empty_does_nothing(self) -> None:
        """验证刷新空会对应的测试场景。"""
        ps = PulseShaper()
        bus = AsyncMock()
        await ps._flush(bus)
        bus.publish.assert_not_awaited()


class TestMultipleCorrelations:
    """验证测试多个行为的测试集合。"""

    @pytest.mark.asyncio
    async def test_batch_uses_first_event_correlation(self) -> None:
        """验证批次使用第一事件关联对应的测试场景。"""
        ps = PulseShaper(window_seconds=10.0, max_batch_size=2)
        bus = AsyncMock()

        await ps.on_event(_make_event("a", "corr-aaa"), bus)
        await ps.on_event(_make_event("b", "corr-aaa"), bus)

        published = bus.publish.call_args[0][0]
        assert published.correlation_id == "corr-aaa"
        assert published.source_agent == "pulse-shaper"
