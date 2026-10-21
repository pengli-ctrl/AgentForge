"""熔断器模块。"""

from __future__ import annotations

import enum
import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class CircuitState(enum.Enum):
    """熔断器状态枚举。"""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """熔断器领域组件。"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """初始化 CircuitBreaker。

        Args:
            failure_threshold: 失败阈值。
            recovery_timeout: 超时。
            half_open_max_calls: 一半打开最大调用。
            clock: 输入参数。
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._clock = clock or time.monotonic

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls: int = 0

    @property
    def state(self) -> CircuitState:
        """当前熔断器状态。

        Returns:
            熔断状态结果。
        """
        if self._state == CircuitState.OPEN:
            if self._clock() - self._last_failure_time >= self.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
                logger.info(
                    "Circuit breaker transitioning OPEN -> HALF_OPEN " "(recovery timeout elapsed)"
                )
        return self._state

    def can_execute(self) -> bool:
        """判断是否允许执行请求。

        Returns:
            操作是否成功。
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
        """记录一次成功调用。"""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            logger.info("Circuit breaker HALF_OPEN -> CLOSED " "(trial request succeeded)")
            self._transition_to(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            # 重置失败计数（连续失败被打断）
            self._failure_count = 0

    def record_failure(self) -> None:
        """记录一次失败调用。"""
        if self._state == CircuitState.CLOSED:
            self._failure_count += 1
            self._last_failure_time = self._clock()

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
            self._last_failure_time = self._clock()

    def reset(self) -> None:
        """重置当前状态。"""
        self._transition_to(CircuitState.CLOSED)
        logger.info("Circuit breaker manually reset to CLOSED")

    def _transition_to(self, new_state: CircuitState) -> None:
        """执行状态转换，重置相关计数器。

        Args:
            new_state: 状态。
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
                self._last_failure_time = self._clock()
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._failure_count = 0

    @property
    def failure_count(self) -> int:
        """当前连续失败次数。

        Returns:
            整数结果。
        """
        return self._failure_count

    def __repr__(self) -> str:
        """返回 CircuitBreaker 的调试字符串表示。

        Returns:
            字符串结果。
        """
        return (
            f"CircuitBreaker(state={self._state.value}, "
            f"failures={self._failure_count}, "
            f"threshold={self.failure_threshold})"
        )
