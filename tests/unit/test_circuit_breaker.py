"""CircuitBreaker 单元测试 — 熔断器状态机。

测试要点：状态转换、失败计数、恢复超时、半开试探。
"""

from __future__ import annotations

import time

from agentforge.core.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitState:
    """CircuitState 枚举测试。"""

    def test_three_states_exist(self) -> None:
        assert CircuitState.CLOSED
        assert CircuitState.OPEN
        assert CircuitState.HALF_OPEN

    def test_state_values(self) -> None:
        assert CircuitState.CLOSED.value == "CLOSED"
        assert CircuitState.OPEN.value == "OPEN"
        assert CircuitState.HALF_OPEN.value == "HALF_OPEN"

    def test_states_are_distinct(self) -> None:
        states = {CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN}
        assert len(states) == 3


class TestCircuitBreakerInit:
    """初始化测试。"""

    def test_default_parameters(self) -> None:
        breaker = CircuitBreaker()
        assert breaker.failure_threshold == 5
        assert breaker.recovery_timeout == 60.0
        assert breaker.half_open_max_calls == 1
        assert breaker.state == CircuitState.CLOSED

    def test_custom_parameters(self) -> None:
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
            half_open_max_calls=2,
        )
        assert breaker.failure_threshold == 3
        assert breaker.recovery_timeout == 30.0
        assert breaker.half_open_max_calls == 2

    def test_initial_failure_count_zero(self) -> None:
        breaker = CircuitBreaker()
        assert breaker.failure_count == 0


class TestClosedState:
    """CLOSED 状态测试。"""

    def test_can_execute_in_closed(self) -> None:
        breaker = CircuitBreaker()
        assert breaker.can_execute() is True

    def test_record_success_resets_failure_count(self) -> None:
        breaker = CircuitBreaker(failure_threshold=5)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.failure_count == 2
        breaker.record_success()
        assert breaker.failure_count == 0

    def test_record_failure_increments_count(self) -> None:
        breaker = CircuitBreaker(failure_threshold=5)
        for i in range(4):
            breaker.record_failure()
            assert breaker.failure_count == i + 1
            assert breaker.state == CircuitState.CLOSED

    def test_transition_to_open_after_threshold(self) -> None:
        breaker = CircuitBreaker(failure_threshold=3)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED
        breaker.record_failure()  # 第 3 次失败
        assert breaker.state == CircuitState.OPEN

    def test_can_execute_after_open(self) -> None:
        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.can_execute() is False


class TestOpenState:
    """OPEN 状态测试。"""

    def test_can_execute_false_in_open(self) -> None:
        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.can_execute() is False

    def test_stays_open_before_recovery_timeout(self) -> None:
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        breaker.record_failure()
        # 立即检查，不应恢复
        assert breaker.state == CircuitState.OPEN
        assert breaker.can_execute() is False

    def test_transitions_to_half_open_after_timeout(self) -> None:
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        time.sleep(0.15)

        # state property 应自动转换到 HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN

    def test_record_failure_in_open_extends_timer(self) -> None:
        """OPEN 状态下 record_failure 应重置计时器。"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.2)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        time.sleep(0.15)

        # 在恢复前再次失败，重置计时器
        breaker.record_failure()
        time.sleep(0.15)

        # 仍应该是 OPEN（因为计时器被重置）
        assert breaker.state == CircuitState.OPEN


class TestHalfOpenState:
    """HALF_OPEN 状态测试。"""

    def test_can_execute_allows_one_call_in_half_open(self) -> None:
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.05,
            half_open_max_calls=1,
        )
        breaker.record_failure()
        time.sleep(0.06)

        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker.can_execute() is True
        # 第二次调用应被拒绝
        assert breaker.can_execute() is False

    def test_half_open_success_recovers_to_closed(self) -> None:
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.05,
        )
        breaker.record_failure()
        time.sleep(0.06)

        assert breaker.state == CircuitState.HALF_OPEN
        breaker.can_execute()  # 消耗一次试探
        breaker.record_success()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_half_open_failure_back_to_open(self) -> None:
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.05,
        )
        breaker.record_failure()
        time.sleep(0.06)

        assert breaker.state == CircuitState.HALF_OPEN
        breaker.can_execute()  # 消耗一次试探
        breaker.record_failure()

        assert breaker.state == CircuitState.OPEN

    def test_half_open_with_multiple_allowed_calls(self) -> None:
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.05,
            half_open_max_calls=3,
        )
        breaker.record_failure()
        time.sleep(0.06)

        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker.can_execute() is True
        assert breaker.can_execute() is True
        assert breaker.can_execute() is True
        assert breaker.can_execute() is False  # 超过限制


class TestStateTransitions:
    """完整状态转换链测试。"""

    def test_full_cycle_closed_open_half_open_closed(self) -> None:
        """完整状态转换链：CLOSED → OPEN → HALF_OPEN → CLOSED。"""
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=0.05,
        )

        # CLOSED → OPEN
        assert breaker.state == CircuitState.CLOSED
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # OPEN → HALF_OPEN
        time.sleep(0.06)
        assert breaker.state == CircuitState.HALF_OPEN

        # HALF_OPEN → CLOSED
        breaker.can_execute()
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_full_cycle_with_half_open_failure(self) -> None:
        """完整状态转换链：CLOSED → OPEN → HALF_OPEN → OPEN → HALF_OPEN → CLOSED。"""
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.05,
        )

        # CLOSED → OPEN
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # OPEN → HALF_OPEN
        time.sleep(0.06)
        assert breaker.state == CircuitState.HALF_OPEN

        # HALF_OPEN → OPEN (试探失败)
        breaker.can_execute()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # OPEN → HALF_OPEN (再次等待恢复)
        time.sleep(0.06)
        assert breaker.state == CircuitState.HALF_OPEN

        # HALF_OPEN → CLOSED (试探成功)
        breaker.can_execute()
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED


class TestReset:
    """reset 方法测试。"""

    def test_reset_from_open(self) -> None:
        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_reset_from_half_open(self) -> None:
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.05,
        )
        breaker.record_failure()
        time.sleep(0.06)
        assert breaker.state == CircuitState.HALF_OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED

    def test_reset_from_closed(self) -> None:
        breaker = CircuitBreaker(failure_threshold=5)
        breaker.record_failure()
        breaker.record_failure()

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0


class TestRepr:
    """__repr__ 测试。"""

    def test_repr_contains_state(self) -> None:
        breaker = CircuitBreaker(failure_threshold=3)
        r = repr(breaker)
        assert "CLOSED" in r
        assert "failures=0" in r

    def test_repr_updates_with_state(self) -> None:
        breaker = CircuitBreaker(failure_threshold=1)
        breaker.record_failure()
        r = repr(breaker)
        assert "OPEN" in r
        assert "failures=1" in r


class TestRealWorldScenarios:
    """真实场景模拟测试。"""

    def test_simulate_agent_failures_and_recovery(self) -> None:
        """模拟 Agent 调用失败→熔断→恢复的完整场景。"""
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=0.05,
        )

        # 正常调用
        assert breaker.can_execute()
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

        # Agent 开始连续失败
        for _ in range(3):
            assert breaker.can_execute()
            breaker.record_failure()

        # 熔断中，快速失败
        assert breaker.state == CircuitState.OPEN
        assert not breaker.can_execute()

        # 等待恢复
        time.sleep(0.06)

        # 半开试探
        assert breaker.can_execute()  # 允许试探
        breaker.record_success()

        # 恢复正常
        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_execute()

    def test_simulate_intermittent_failures(self) -> None:
        """间歇性失败不应立即熔断（成功打断失败计数）。"""
        breaker = CircuitBreaker(failure_threshold=3)

        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()  # 成功重置计数
        breaker.record_failure()
        breaker.record_failure()

        # 只有 2 次连续失败，不应熔断
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 2
