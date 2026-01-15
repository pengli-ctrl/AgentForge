"""AgentForge 编排执行层：request_guard。

本模块负责 request_guard 相关能力，是 编排执行层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：RequestGuard。
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RequestGuard:
    """RequestGuard。

    RequestGuard 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - MAX_DAG_NODES: 50。
    - MAX_LLM_CALLS_PER_REQUEST: 100。
    - MAX_ACTIVE_DAGS: 10。
    - MAX_PARALLEL_NODES: 5。
    - 方法 check_dag_size()。
    - 方法 check_llm_call_count()。
    - 方法 check_concurrency()。
    - 方法 acquire()。
    - 方法 release()。
    - 方法 increment_llm_calls()。
    - 方法 get_llm_call_count()。
    - 方法 cleanup_request()。
    - 方法 active_dag_count()。
    - 方法 available_slots()。
    - 方法 status()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    MAX_DAG_NODES = 50  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    MAX_LLM_CALLS_PER_REQUEST = 100  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    MAX_ACTIVE_DAGS = 10  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    MAX_PARALLEL_NODES = 5  # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    def __init__(
        self,
        max_active_dags: Optional[int] = None,
        max_parallel_nodes: Optional[int] = None,
    ):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            max_active_dags: Optional[int]，调用方传入的 max_active_dags 参数。
            max_parallel_nodes: Optional[int]，调用方传入的 max_parallel_nodes 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._max_active = max_active_dags or self.MAX_ACTIVE_DAGS
        self._max_parallel = max_parallel_nodes or self.MAX_PARALLEL_NODES
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._semaphore = asyncio.Semaphore(self._max_active * self._max_parallel)
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._active_dag_count = 0
        self._dag_count_lock = asyncio.Lock()
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._llm_call_counts: dict[str, int] = {}  # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    def check_dag_size(self, node_count: int) -> bool:
        """执行 check_dag_size 对应的逻辑，并返回处理结果。

        Args:
            node_count: int，调用方传入的 node_count 参数。

        Returns:
            bool，函数执行后的结果。
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
        """执行 check_llm_call_count 对应的逻辑，并返回处理结果。

        Args:
            current_count: int，调用方传入的 current_count 参数。

        Returns:
            bool，函数执行后的结果。
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
        """执行 check_concurrency 对应的逻辑，并返回处理结果。

        Args:
            active_dags: int，调用方传入的 active_dags 参数。
            parallel_nodes: int，调用方传入的 parallel_nodes 参数。

        Returns:
            bool，函数执行后的结果。
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

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    async def acquire(self) -> bool:
        """执行 acquire 对应的逻辑，并返回处理结果。

        Returns:
            bool，函数执行后的结果。
        """
        await self._semaphore.acquire()
        async with self._dag_count_lock:
            self._active_dag_count += 1
        return True

    async def release(self) -> None:
        """执行 release 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        self._semaphore.release()
        async with self._dag_count_lock:
            self._active_dag_count = max(0, self._active_dag_count - 1)

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    def increment_llm_calls(self, correlation_id: str) -> int:
        """执行 increment_llm_calls 对应的逻辑，并返回处理结果。

        Args:
            correlation_id: str，调用方传入的 correlation_id 参数。

        Returns:
            int，函数执行后的结果。
        """
        self._llm_call_counts[correlation_id] = self._llm_call_counts.get(correlation_id, 0) + 1
        return self._llm_call_counts[correlation_id]

    def get_llm_call_count(self, correlation_id: str) -> int:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            correlation_id: str，调用方传入的 correlation_id 参数。

        Returns:
            int，函数执行后的结果。
        """
        return self._llm_call_counts.get(correlation_id, 0)

    def cleanup_request(self, correlation_id: str) -> None:
        """执行 cleanup_request 对应的逻辑，并返回处理结果。

        Args:
            correlation_id: str，调用方传入的 correlation_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._llm_call_counts.pop(correlation_id, None)

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    @property
    def active_dag_count(self) -> int:
        """执行 active_dag_count 对应的逻辑，并返回处理结果。

        Returns:
            int，函数执行后的结果。
        """
        return self._active_dag_count

    @property
    def available_slots(self) -> int:
        """执行 available_slots 对应的逻辑，并返回处理结果。

        Returns:
            int，函数执行后的结果。
        """
        return self._semaphore._value

    def status(self) -> dict:
        """执行 status 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
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
