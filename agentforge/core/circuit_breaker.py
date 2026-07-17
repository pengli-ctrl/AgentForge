"""
熔断器 — Agent 调用的自动故障隔离（博客 06 Layer 1）。

当某个 Agent 连续失败时，熔断器自动切断对该 Agent 的调用，
防止故障扩散到整个系统。

状态机（三态）：
    CLOSED ──(连续失败 N 次)──> OPEN
    OPEN ──(等待 T 秒)──> HALF_OPEN
    HALF_OPEN ──(试探成功)──> CLOSED
    HALF_OPEN ──(试探失败)──> OPEN（重置计时器）

    CLOSED: 正常状态，所有请求放行
    OPEN: 熔断状态，所有请求被拒绝（快速失败）
    HALF_OPEN: 半开状态，允许一次试探请求
        - 试探成功 → 恢复到 CLOSED
        - 试探失败 → 重新回到 OPEN

设计参数：
- failure_threshold = 5: 连续 5 次失败触发熔断
- recovery_timeout = 60s: 熔断后等待 60 秒再尝试恢复
- half_open_max_calls = 1: 半开状态只允许 1 次试探

使用方式：
    breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

    if breaker.can_execute():
        try:
            result = await agent.execute(event)
            breaker.record_success()
        except Exception:
            breaker.record_failure()
    else:
        # 熔断中，走降级逻辑
        result = fallback_handler()
"""

from __future__ import annotations

import enum
import logging
import time

logger = logging.getLogger(__name__)


class CircuitState(enum.Enum):
    """熔断器状态枚举。

    Attributes:
        CLOSED: 正常状态，请求放行。
        OPEN: 熔断状态，请求被拒绝。
        HALF_OPEN: 半开状态，允许一次试探请求。
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """熔断器 — Agent 调用的自动故障隔离。

    通过状态机管理 Agent 的调用权限：
    - CLOSED 状态下正常放行请求
    - 连续失败达到阈值后切换到 OPEN 状态
    - OPEN 状态下经过恢复时间后切换到 HALF_OPEN
    - HALF_OPEN 状态下试探请求的结果决定恢复或重新熔断

    线程安全说明：本实现非线程安全，适用于单线程异步场景
    （Agent 执行是串行的，不需要锁）。

    Args:
        failure_threshold: 连续失败多少次后触发熔断（默认 5）。
        recovery_timeout: 熔断后等待多少秒才尝试恢复（默认 60）。
        half_open_max_calls: 半开状态下允许的试探次数（默认 1）。
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls: int = 0

    @property
    def state(self) -> CircuitState:
        """当前熔断器状态。

        如果当前是 OPEN 状态且已超过恢复时间，自动切换到 HALF_OPEN。

        Returns:
            当前 CircuitState 枚举值。
        """
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
                logger.info(
                    "Circuit breaker transitioning OPEN -> HALF_OPEN " "(recovery timeout elapsed)"
                )
        return self._state

    def can_execute(self) -> bool:
        """判断是否允许执行请求。

        状态逻辑：
        - CLOSED: 始终允许
        - OPEN: 拒绝（但会检查是否已过恢复时间，如果过了则切换到 HALF_OPEN）
        - HALF_OPEN: 只允许 half_open_max_calls 次试探

        Returns:
            是否允许执行。
        """
        current = self.state  # 触发 OPEN -> HALF_OPEN 的自动转换

        if current == CircuitState.CLOSED:
            return True

        if current == CircuitState.OPEN:
            return False

        # HALF_OPEN: 只允许有限次试探
        if current == CircuitState.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

        return False

    def record_success(self) -> None:
        """记录一次成功调用。

        状态转换：
        - CLOSED: 重置失败计数
        - HALF_OPEN: 恢复到 CLOSED（试探成功，恢复正常）
        - OPEN: 不应该收到 success（can_execute 返回 False）
        """
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            logger.info("Circuit breaker HALF_OPEN -> CLOSED " "(trial request succeeded)")
            self._transition_to(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            # 重置失败计数（连续失败被打断）
            self._failure_count = 0

    def record_failure(self) -> None:
        """记录一次失败调用。

        状态转换：
        - CLOSED: 增加失败计数，达到阈值后切换到 OPEN
        - HALF_OPEN: 切换回 OPEN（试探失败，重新熔断）
        - OPEN: 更新最后失败时间（重置计时器）
        """
        if self._state == CircuitState.CLOSED:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._failure_count >= self.failure_threshold:
                logger.warning(
                    "Circuit breaker CLOSED -> OPEN " "(consecutive failures=%d, threshold=%d)",
                    self._failure_count,
                    self.failure_threshold,
                )
                self._transition_to(CircuitState.OPEN)

        elif self._state == CircuitState.HALF_OPEN:
            logger.warning(
                "Circuit breaker HALF_OPEN -> OPEN " "(trial request failed, resetting timer)"
            )
            self._transition_to(CircuitState.OPEN)

        elif self._state == CircuitState.OPEN:
            # 已经在 OPEN 状态，更新失败时间（延长恢复等待）
            self._last_failure_time = time.monotonic()

    def reset(self) -> None:
        """重置熔断器到初始状态（CLOSED）。

        用于手动恢复或测试场景。
        """
        self._transition_to(CircuitState.CLOSED)
        logger.info("Circuit breaker manually reset to CLOSED")

    def _transition_to(self, new_state: CircuitState) -> None:
        """执行状态转换，重置相关计数器。

        Args:
            new_state: 目标状态。
        """
        old_state = self._state
        self._state = new_state

        # 根据新状态重置计数器
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.OPEN:
            self._half_open_calls = 0
            if old_state != CircuitState.OPEN:
                # 仅在从其他状态转入 OPEN 时更新时间
                self._last_failure_time = time.monotonic()
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._failure_count = 0

    @property
    def failure_count(self) -> int:
        """当前连续失败次数。"""
        return self._failure_count

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self._state.value}, "
            f"failures={self._failure_count}, "
            f"threshold={self.failure_threshold})"
        )
