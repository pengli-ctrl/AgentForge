"""AIMD控制器模块。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AIMDRetryController:
    """基于 AIMD 策略的重试与限流控制器。"""

    def __init__(self) -> None:
        """初始化 AIMDRetryController。"""
        self.congestion_window: float = 10.0  # 拥塞窗口（类似 TCP cwnd）
        self.slow_start_threshold: float = 20.0  # 慢启动阈值
        self.current_rto: float = 5.0  # 当前重试超时（Retry Timeout）
        self.min_rto: float = 1.0
        self.max_rto: float = 60.0

    def on_success(self) -> None:
        """请求成功 → 线性增加拥塞窗口（类似 TCP 拥塞避免）。"""
        self.congestion_window = min(
            self.congestion_window + 1.0,
            self.slow_start_threshold,
        )
        # 逐步恢复正常重试超时
        self.current_rto = max(self.current_rto * 0.9, self.min_rto)

        logger.debug(
            "AIMD on_success (cwnd=%.1f, rto=%.1f)",
            self.congestion_window,
            self.current_rto,
        )

    def on_timeout(self) -> None:
        """超时 → 乘性减少（类似 TCP 快重传）。"""
        self.congestion_window = max(self.congestion_window / 2, 1.0)
        self.slow_start_threshold = self.congestion_window
        # 指数退避重试超时
        self.current_rto = min(self.current_rto * 2, self.max_rto)

        logger.warning(
            "AIMD on_timeout (cwnd=%.1f, ssthresh=%.1f, rto=%.1f)",
            self.congestion_window,
            self.slow_start_threshold,
            self.current_rto,
        )

    def get_max_concurrent_retries(self) -> int:
        """当前允许的最大并发重试数 = 拥塞窗口。

        Returns:
            整数结果。
        """
        return max(1, int(self.congestion_window))

    def get_retry_delay(self) -> float:
        """当前重试延迟。

        Returns:
            数值结果。
        """
        return self.current_rto


class GlobalPriorityQueue:
    """全局优先级队列 — 防止低优先级重试挤占高优先级请求。

    Attributes:
        PRIORITY_LEVELS: 优先级。
    """

    PRIORITY_LEVELS: dict[str, int] = {
        "user_sync": 0,  # 用户同步请求（人在等）— 最高
        "task_primary": 1,  # 任务主链路请求
        "task_retry": 2,  # 任务重试请求
        "batch": 3,  # 批处理任务 — 最低
    }

    def __init__(self, max_queue_size: int = 100) -> None:
        """初始化全局优先级队列。

        Args:
            max_queue_size: 最大队列大小。
        """
        from collections import deque

        self.queues: dict[int, deque] = {level: deque() for level in self.PRIORITY_LEVELS.values()}
        self.max_size = max_queue_size

    async def submit(self, request: Any) -> Any:
        """提交请求到优先级队列。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            处理结果对象。

        Raises:
            QueueFullError: 操作无法完成时抛出。
        """
        priority = self.PRIORITY_LEVELS.get(getattr(request, "priority_class", "task_retry"), 2)

        # 队列满时，低优先级请求被拒绝（保护高优先级）
        total_queued = sum(len(q) for q in self.queues.values())
        if total_queued >= self.max_size and priority > 0:
            raise QueueFullError(
                f"Queue full ({total_queued}/{self.max_size}). " f"Low-priority request rejected."
            )

        self.queues[priority].append(request)

        # 按优先级出队
        for level in sorted(self.queues.keys()):
            if self.queues[level]:
                req = self.queues[level].popleft()
                return await self._process(req)

        return None

    async def _process(self, request: Any) -> Any:
        """执行请求，带硬性超时。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            处理结果对象。

        Raises:
            Exception: 操作无法完成时抛出。
        """
        import asyncio

        try:
            return await asyncio.wait_for(
                self._execute(request),
                timeout=getattr(request, "timeout", 30.0),
            )
        except asyncio.TimeoutError:
            # 超时后不自动重试——由 AIMD 控制器决定是否重试
            raise

    async def _execute(self, request: Any) -> Any:
        """执行核心处理逻辑并返回结果。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            处理结果对象。
        """
        # 实际实现取决于具体的 LLM Gateway
        return None


class QueueFullError(Exception):
    """队列满异常 — 低优先级请求被拒绝时抛出。"""
