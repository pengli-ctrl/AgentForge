"""AIMD 拥塞控制器单元测试 — 加性增长/乘性减少窗口调整。

测试要点：加性增加/乘性减少窗口调整、拥塞检测、窗口恢复、阈值计算。
"""

from __future__ import annotations

import pytest

from agentforge.safety.aimd_controller import (
    AIMDRetryController,
    GlobalPriorityQueue,
    QueueFullError,
)


class TestAIMDRetryControllerInit:
    """初始化测试。"""

    def test_default_values(self) -> None:
        ctrl = AIMDRetryController()
        assert ctrl.congestion_window == 10.0
        assert ctrl.slow_start_threshold == 20.0
        assert ctrl.current_rto == 5.0
        assert ctrl.min_rto == 1.0
        assert ctrl.max_rto == 60.0


class TestAdditiveIncrease:
    """加性增加测试。"""

    def test_success_increases_window_by_one(self) -> None:
        ctrl = AIMDRetryController()
        initial = ctrl.congestion_window
        ctrl.on_success()
        assert ctrl.congestion_window == initial + 1.0

    def test_success_capped_at_threshold(self) -> None:
        ctrl = AIMDRetryController()
        ctrl.congestion_window = 19.5
        ctrl.slow_start_threshold = 20.0
        ctrl.on_success()
        assert ctrl.congestion_window == 20.0

    def test_success_decreases_rto(self) -> None:
        ctrl = AIMDRetryController()
        initial_rto = ctrl.current_rto
        ctrl.on_success()
        assert ctrl.current_rto < initial_rto
        assert ctrl.current_rto == pytest.approx(initial_rto * 0.9)

    def test_rto_capped_at_min(self) -> None:
        ctrl = AIMDRetryController()
        ctrl.current_rto = 1.05
        ctrl.on_success()
        assert ctrl.current_rto == ctrl.min_rto


class TestMultiplicativeDecrease:
    """乘性减少测试。"""

    def test_timeout_halves_window(self) -> None:
        ctrl = AIMDRetryController()
        ctrl.congestion_window = 10.0
        ctrl.on_timeout()
        assert ctrl.congestion_window == 5.0

    def test_timeout_updates_threshold(self) -> None:
        ctrl = AIMDRetryController()
        ctrl.congestion_window = 10.0
        ctrl.on_timeout()
        assert ctrl.slow_start_threshold == 5.0

    def test_timeout_doubles_rto(self) -> None:
        ctrl = AIMDRetryController()
        initial_rto = ctrl.current_rto
        ctrl.on_timeout()
        assert ctrl.current_rto == initial_rto * 2

    def test_timeout_rto_capped_at_max(self) -> None:
        ctrl = AIMDRetryController()
        ctrl.current_rto = 50.0
        ctrl.on_timeout()
        assert ctrl.current_rto == ctrl.max_rto

    def test_window_floored_at_one(self) -> None:
        ctrl = AIMDRetryController()
        ctrl.congestion_window = 1.5
        ctrl.on_timeout()
        assert ctrl.congestion_window == 1.0  # max(0.75, 1.0) = 1.0


class TestMaxConcurrentRetries:
    """最大并发重试数测试。"""

    def test_returns_int_floor_of_window(self) -> None:
        ctrl = AIMDRetryController()
        ctrl.congestion_window = 7.8
        assert ctrl.get_max_concurrent_retries() == 7

    def test_minimum_one(self) -> None:
        ctrl = AIMDRetryController()
        ctrl.congestion_window = 0.5
        assert ctrl.get_max_concurrent_retries() == 1


class TestRetryDelay:
    """重试延迟测试。"""

    def test_returns_current_rto(self) -> None:
        ctrl = AIMDRetryController()
        ctrl.current_rto = 12.0
        assert ctrl.get_retry_delay() == 12.0


class TestGlobalPriorityQueue:
    """全局优先级队列测试。"""

    def test_priority_levels(self) -> None:
        assert GlobalPriorityQueue.PRIORITY_LEVELS["user_sync"] == 0
        assert GlobalPriorityQueue.PRIORITY_LEVELS["task_primary"] == 1
        assert GlobalPriorityQueue.PRIORITY_LEVELS["task_retry"] == 2
        assert GlobalPriorityQueue.PRIORITY_LEVELS["batch"] == 3

    def test_init_creates_queues(self) -> None:
        q = GlobalPriorityQueue(max_queue_size=50)
        assert q.max_size == 50
        assert len(q.queues) == 4

    @pytest.mark.asyncio
    async def test_submit_rejects_low_priority_when_full(self) -> None:
        q = GlobalPriorityQueue(max_queue_size=1)

        # 预填内部队列（绕过 submit 的立即出队机制）

        q.queues[0].append(object())  # priority 0 = highest, 占满队列

        class _LowReq:
            priority_class: str = "batch"  # priority > 0, 低优先级
            timeout: float = 5.0

        with pytest.raises(QueueFullError):
            await q.submit(_LowReq())

    def test_queue_full_error_is_exception(self) -> None:
        assert issubclass(QueueFullError, Exception)
