"""
AIMD 拥塞控制器 — 基于 TCP AIMD 原理的全局重试控制。

解决超时重试引发的资源拥塞崩溃：
当多个 Agent 的超时重试在时间上重叠时，重试流量本身变成了新的负载来源，
与原始流量叠加后超过了共享资源的承载能力。

核心思想：重试速率不是每个 Agent 独立决定的，
而是根据共享资源的拥塞程度全局调整。

AIMD（Additive Increase Multiplicative Decrease）：
- 请求成功 → 线性增加拥塞窗口（加性增加）
- 超时 → 乘性减少拥塞窗口（乘性减少）
- 类似 TCP Tahoe/Reno/CUBIC 的拥塞控制机制
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AIMDRetryController:
    """基于 TCP AIMD 原理的拥塞控制重试器。

    核心思想：重试速率不是每个 Agent 独立决定的，
    而是根据共享资源的拥塞程度全局调整。

    每个参与者的"合理重试"在聚合后变成了系统性过载。
    必须有一个全局的拥塞控制器来协调所有 Agent 的重试行为。

    属性说明：
    - congestion_window: 拥塞窗口（类似 TCP cwnd），控制最大并发重试数
    - slow_start_threshold: 慢启动阈值
    - current_rto: 当前重试超时（Retry Timeout）
    - min_rto / max_rto: RTO 的上下限

    Example:
        >>> controller = AIMDRetryController()
        >>> try:
        ...     response = await llm.chat(prompt)
        ...     controller.on_success()
        ... except TimeoutError:
        ...     controller.on_timeout()
        ...     delay = controller.get_retry_delay()
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self.congestion_window: float = 10.0  # 拥塞窗口（类似 TCP cwnd）
        self.slow_start_threshold: float = 20.0  # 慢启动阈值
        self.current_rto: float = 5.0  # 当前重试超时（Retry Timeout）
        self.min_rto: float = 1.0
        self.max_rto: float = 60.0

    def on_success(self) -> None:
        """请求成功 → 线性增加拥塞窗口（类似 TCP 拥塞避免）。

        成功时逐步放开并发限制，恢复正常吞吐量。
        同时逐步缩短重试超时，加快恢复速度。
        """
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
        """超时 → 乘性减少（类似 TCP 快重传）。

        超时时立即减半拥塞窗口，限制并发重试数。
        同时指数退避重试超时，给共享资源恢复时间。
        """
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
            最大并发重试数。
        """
        return max(1, int(self.congestion_window))

    def get_retry_delay(self) -> float:
        """当前重试延迟。

        Returns:
            重试延迟（秒）。
        """
        return self.current_rto


class GlobalPriorityQueue:
    """全局优先级队列 — 防止低优先级重试挤占高优先级请求。

    解决超时重试场景中的优先级反转问题：
    CodeReview 的快速重试密集占满 LLM 请求队列，
    DocGenerator 的高优先级任务排在重试请求后面，
    等待时间从正常的 2s 变成 60s+。

    四级优先级：
    - user_sync (0): 用户同步请求（人在等）— 最高
    - task_primary (1): 任务主链路请求
    - task_retry (2): 任务重试请求
    - batch (3): 批处理任务 — 最低

    队列满时低优先级请求被拒绝（快速失败优于排队等待）。
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

        队列满时，低优先级请求被拒绝（保护高优先级）。
        按优先级出队处理。

        Args:
            request: 请求对象，需包含 priority_class 属性。

        Returns:
            请求处理结果。

        Raises:
            QueueFullError: 队列满且请求为低优先级时。
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

        超时后不自动重试 — 由 AIMD 控制器决定是否重试。

        Args:
            request: 请求对象。

        Returns:
            请求处理结果。
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
        """执行具体请求（子类实现）。

        Args:
            request: 请求对象。

        Returns:
            请求处理结果。
        """
        # 实际实现取决于具体的 LLM Gateway
        return None


class QueueFullError(Exception):
    """队列满异常 — 低优先级请求被拒绝时抛出。"""
