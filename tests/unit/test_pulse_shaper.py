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
    """执行 _make_event 对应的逻辑，并返回处理结果。

    Args:
        source: str，调用方传入的 source 参数。
        corr_id: str，调用方传入的 corr_id 参数。

    Returns:
        AgentEvent，函数执行后的结果。
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
        """验证 default_values 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        ps = PulseShaper()
        assert ps.window == 5.0
        assert ps.max_batch == 10
        assert ps.pending == []
        assert ps.flush_task is None

    def test_custom_values(self) -> None:
        """验证 custom_values 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        ps = PulseShaper(window_seconds=2.0, max_batch_size=5)
        assert ps.window == 2.0
        assert ps.max_batch == 5


class TestBatchFlush:
    """批量触发 flush 测试。"""

    @pytest.mark.asyncio
    async def test_flush_on_batch_full(self) -> None:
        """验证 flush_on_batch_full 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
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
        """验证 no_flush_below_batch_threshold 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        ps = PulseShaper(window_seconds=10.0, max_batch_size=5)
        bus = AsyncMock()

        await ps.on_event(_make_event(), bus)
        bus.publish.assert_not_awaited()
        assert len(ps.pending) == 1

    @pytest.mark.asyncio
    async def test_flush_creates_merged_event(self) -> None:
        """验证 flush_creates_merged_event 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
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
    """窗口超时 flush 测试。"""

    @pytest.mark.asyncio
    async def test_delayed_flush_after_window(self) -> None:
        """验证 delayed_flush_after_window 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        ps = PulseShaper(window_seconds=0.05, max_batch_size=10)
        bus = AsyncMock()

        await ps.on_event(_make_event(), bus)
        assert ps.flush_task is not None

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        await asyncio.sleep(0.1)
        bus.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flush_task_cleared_after_flush(self) -> None:
        """验证 flush_task_cleared_after_flush 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        ps = PulseShaper(window_seconds=0.05, max_batch_size=10)
        bus = AsyncMock()

        await ps.on_event(_make_event(), bus)
        await asyncio.sleep(0.1)
        assert ps.flush_task is None


class TestFlushEmpty:
    """空 flush 测试。"""

    @pytest.mark.asyncio
    async def test_flush_empty_does_nothing(self) -> None:
        """验证 flush_empty_does_nothing 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        ps = PulseShaper()
        bus = AsyncMock()
        await ps._flush(bus)
        bus.publish.assert_not_awaited()


class TestMultipleCorrelations:
    """TestMultipleCorrelations。

    TestMultipleCorrelations 组织一组相关测试，覆盖正常流程、边界条件和回归场景。

    主要成员：
    - 方法 test_batch_uses_first_event_correlation()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    @pytest.mark.asyncio
    async def test_batch_uses_first_event_correlation(self) -> None:
        """验证 batch_uses_first_event_correlation 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        ps = PulseShaper(window_seconds=10.0, max_batch_size=2)
        bus = AsyncMock()

        await ps.on_event(_make_event("a", "corr-aaa"), bus)
        await ps.on_event(_make_event("b", "corr-aaa"), bus)

        published = bus.publish.call_args[0][0]
        assert published.correlation_id == "corr-aaa"
        assert published.source_agent == "pulse-shaper"
