"""请求模块。"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RequestGuard:
    """请求相关组件。"""

    MAX_DAG_NODES = 50
    MAX_LLM_CALLS_PER_REQUEST = 100
    MAX_ACTIVE_DAGS = 10
    MAX_PARALLEL_NODES = 5

    def __init__(
        self,
        max_active_dags: Optional[int] = None,
        max_parallel_nodes: Optional[int] = None,
    ):
        """初始化 RequestGuard。

        Args:
            max_active_dags: 最大活跃。
            max_parallel_nodes: 最大。
        """
        self._max_active = max_active_dags or self.MAX_ACTIVE_DAGS
        self._max_parallel = max_parallel_nodes or self.MAX_PARALLEL_NODES
        self._semaphore = asyncio.Semaphore(self._max_active * self._max_parallel)
        self._active_dag_count = 0
        self._dag_count_lock = asyncio.Lock()
        self._llm_call_counts: dict[str, int] = {}

    def check_dag_size(self, node_count: int) -> bool:
        """检查DAG大小。

        Args:
            node_count: 数量。

        Returns:
            操作是否成功。
        """
        if node_count > self.MAX_DAG_NODES:
            logger.warning(
                "DAG size check FAILED: %d nodes > %d max. " "Consider splitting into sub-DAGs.",
                node_count,
                self.MAX_DAG_NODES,
            )
            return False
        return True

    def check_llm_call_count(self, current_count: int) -> bool:
        """统计检查LLM调用数量。

        Args:
            current_count: 数量。

        Returns:
            操作是否成功。
        """
        if current_count > self.MAX_LLM_CALLS_PER_REQUEST:
            logger.warning(
                "LLM call count check FAILED: %d calls > %d max. " "Request budget exhausted.",
                current_count,
                self.MAX_LLM_CALLS_PER_REQUEST,
            )
            return False
        return True

    def check_concurrency(self, active_dags: int, parallel_nodes: int) -> bool:
        """检查请求。

        Args:
            active_dags: 活跃。
            parallel_nodes: 输入参数。

        Returns:
            操作是否成功。
        """
        if active_dags > self._max_active:
            logger.warning(
                "Concurrency check FAILED: %d active DAGs > %d max",
                active_dags,
                self._max_active,
            )
            return False

        if parallel_nodes > self._max_parallel:
            logger.warning(
                "Concurrency check FAILED: %d parallel nodes > %d max",
                parallel_nodes,
                self._max_parallel,
            )
            return False

        return True

    async def acquire(self) -> bool:
        """获取请求并发或限流许可。

        Returns:
            操作是否成功。
        """
        await self._semaphore.acquire()
        async with self._dag_count_lock:
            self._active_dag_count += 1
        return True

    async def release(self) -> None:
        """处理释放。"""
        self._semaphore.release()
        async with self._dag_count_lock:
            self._active_dag_count = max(0, self._active_dag_count - 1)

    def increment_llm_calls(self, correlation_id: str) -> int:
        """增加 LLM 调用次数。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。

        Returns:
            整数结果。
        """
        self._llm_call_counts[correlation_id] = self._llm_call_counts.get(correlation_id, 0) + 1
        return self._llm_call_counts[correlation_id]

    def get_llm_call_count(self, correlation_id: str) -> int:
        """统计获取LLM调用数量。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。

        Returns:
            整数结果。
        """
        return self._llm_call_counts.get(correlation_id, 0)

    def cleanup_request(self, correlation_id: str) -> None:
        """清理请求。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。
        """
        self._llm_call_counts.pop(correlation_id, None)

    @property
    def active_dag_count(self) -> int:
        """获取当前活跃 DAG 数量。

        Returns:
            整数结果。
        """
        return self._active_dag_count

    @property
    def available_slots(self) -> int:
        """返回当前可用并发槽位。

        Returns:
            整数结果。
        """
        return self._semaphore._value

    def status(self) -> dict:
        """处理状态。

        Returns:
            结构化结果字典。
        """
        return {
            "active_dags": self._active_dag_count,
            "max_active_dags": self._max_active,
            "available_slots": self.available_slots,
            "max_total_slots": self._max_active * self._max_parallel,
            "tracked_requests": len(self._llm_call_counts),
            "limits": {
                "max_dag_nodes": self.MAX_DAG_NODES,
                "max_llm_calls": self.MAX_LLM_CALLS_PER_REQUEST,
                "max_active_dags": self._max_active,
                "max_parallel_nodes": self._max_parallel,
            },
        }
