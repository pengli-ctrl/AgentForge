"""AgentForge 编排执行层：degradation。

本模块负责 degradation 相关能力，是 编排执行层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：DegradationLevel、DegradationEvent、DegradationManager。
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# 说明：该步骤用于实现上述逻辑并保证行为稳定。
CIRCUIT_WINDOW_CALLS = 10  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
CIRCUIT_FAILURE_THRESHOLD = 0.5  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
CIRCUIT_OPEN_DURATION_SECONDS = 900  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
MAX_TRACKED_OUTCOMES = 20  # 说明：该步骤用于实现上述逻辑并保证行为稳定。


class DegradationLevel(Enum):
    """DegradationLevel。

    DegradationLevel 是状态或类型枚举，用于约束系统内部取值，避免散落的字符串常量。

    主要成员：
    - L1_MODEL: 1。
    - L2_NODE: 2。
    - L3_DAG: 3。
    - L4_SYSTEM: 4。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    L1_MODEL = 1  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    L2_NODE = 2  # 失败重试。
    L3_DAG = 3  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    L4_SYSTEM = 4  # 说明：该步骤用于实现上述逻辑并保证行为稳定。


@dataclass
class DegradationEvent:
    """DegradationEvent。

    DegradationEvent 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - level: DegradationLevel。
    - timestamp: float。
    - description: str。
    - action_taken: str。
    - affected_component: str。
    - span_attributes: dict。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    level: DegradationLevel
    timestamp: float
    description: str
    action_taken: str
    affected_component: str
    span_attributes: dict = field(default_factory=dict)


class DegradationManager:
    """DegradationManager。

    DegradationManager 是核心运行时组件，负责状态管理、调度和跨模块协作。

    主要成员：
    - 方法 handle_llm_failure()。
    - 方法 record_llm_success()。
    - 方法 handle_node_failure()。
    - 方法 handle_dag_degradation()。
    - 方法 handle_system_failure()。
    - 方法 reset_dag_counters()。
    - 方法 recover_system()。
    - 方法 is_system_degraded()。
    - 方法 get_recent_events()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._lock = asyncio.Lock()
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._model_calls: dict[str, list[bool]] = (
            {}
        )  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._model_circuit_open: dict[str, float] = (
            {}
        )  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        # 失败重试。
        self._node_retry_counts: dict[str, int] = {}
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._current_dag_failures: int = 0
        self._current_dag_total: int = 0
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._system_degraded: bool = False
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._events: list[DegradationEvent] = []

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    async def handle_llm_failure(self, model_name: str, error: Exception) -> dict:
        """处理输入事件或请求，并返回调用方需要的结果。

        Args:
            model_name: str，调用方传入的 model_name 参数。
            error: Exception，调用方传入的 error 参数。

        Returns:
            dict，函数执行后的结果。
        """
        async with self._lock:
            now = time.time()
            self._record_outcome_locked(model_name, False)
            self._maybe_open_circuit(model_name, now)

        # 降级处理。
        fallback_chain = self._get_fallback_chain(model_name)
        fallback_model = fallback_chain[0] if fallback_chain else None

        event = DegradationEvent(
            level=DegradationLevel.L1_MODEL,
            timestamp=now,
            description=f"Model '{model_name}' failed: {str(error)[:100]}",
            action_taken=f"Fallback to '{fallback_model}'" if fallback_model else "Preset response",
            affected_component=model_name,
            span_attributes={"fallback_model": fallback_model, "error": str(error)[:200]},
        )
        self._events.append(event)

        return {
            "fallback_model": fallback_model,
            "action": "retry_with_fallback" if fallback_model else "preset_response",
            "degraded": True,
        }

    async def record_llm_success(self, model_name: str) -> None:
        """记录事件或指标，并返回调用方需要的结果。

        Args:
            model_name: str，调用方传入的 model_name 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            self._record_outcome_locked(model_name, True)

    def _record_outcome_locked(self, model_name: str, success: bool) -> None:
        """执行 _record_outcome_locked 对应的逻辑，并返回处理结果。

        Args:
            model_name: str，调用方传入的 model_name 参数。
            success: bool，调用方传入的 success 参数。

        Returns:
            None，函数执行后的结果。
        """
        outcomes = self._model_calls.setdefault(model_name, [])
        outcomes.append(success)
        if len(outcomes) > MAX_TRACKED_OUTCOMES:
            del outcomes[:-MAX_TRACKED_OUTCOMES]

    def _maybe_open_circuit(self, model_name: str, now: float) -> None:
        """执行 _maybe_open_circuit 对应的逻辑，并返回处理结果。

        Args:
            model_name: str，调用方传入的 model_name 参数。
            now: float，调用方传入的 now 参数。

        Returns:
            None，函数执行后的结果。
        """
        recent = self._model_calls.get(model_name, [])[-CIRCUIT_WINDOW_CALLS:]
        if len(recent) < CIRCUIT_WINDOW_CALLS:
            return
        failures = sum(1 for ok in recent if not ok)
        failure_rate = failures / len(recent)
        if failure_rate > CIRCUIT_FAILURE_THRESHOLD:
            self._model_circuit_open[model_name] = now + CIRCUIT_OPEN_DURATION_SECONDS
            logger.warning(
                "Circuit breaker OPEN for model: %s (%.0f%% failures over last %d calls)",
                model_name,
                failure_rate * 100,
                CIRCUIT_WINDOW_CALLS,
            )

    def _get_fallback_chain(self, failed_model: str) -> list[str]:
        """执行 _get_fallback_chain 对应的逻辑，并返回处理结果。

        Args:
            failed_model: str，调用方传入的 failed_model 参数。

        Returns:
            list[str]，函数执行后的结果。
        """
        # 成本统计。
        all_models = ["Qwen3-Pro", "GLM-5", "DeepSeek-V3", "Kimi", "MiniMax"]
        now = time.time()
        available = [
            m for m in all_models if m != failed_model and self._model_circuit_open.get(m, 0) < now
        ]
        return available

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    async def handle_node_failure(
        self,
        node_id: str,
        error: Exception,
        retry_count: int = 2,
    ) -> dict:
        """处理输入事件或请求，并返回调用方需要的结果。

        Args:
            node_id: str，调用方传入的 node_id 参数。
            error: Exception，调用方传入的 error 参数。
            retry_count: int，调用方传入的 retry_count 参数。

        Returns:
            dict，函数执行后的结果。
        """
        async with self._lock:
            current_retries = self._node_retry_counts.get(node_id, 0)

            if current_retries < retry_count:
                # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                self._node_retry_counts[node_id] = current_retries + 1
                remaining = retry_count - current_retries - 1
                action = "retry"
                logger.info(
                    "Node[%s] failed, retrying (%d remaining): %s",
                    node_id,
                    remaining,
                    str(error)[:100],
                )
            else:
                # 降级处理。
                action = "fallback_default"
                logger.warning(
                    "Node[%s] exhausted retries (%d/%d), using fallback: %s",
                    node_id,
                    current_retries,
                    retry_count,
                    str(error)[:100],
                )

        event = DegradationEvent(
            level=DegradationLevel.L2_NODE,
            timestamp=time.time(),
            description=f"Node '{node_id}' failed after {current_retries} retries",
            action_taken=action,
            affected_component=node_id,
            span_attributes={"retry_count": current_retries, "error": str(error)[:200]},
        )
        self._events.append(event)

        return {
            "action": action,
            "retry_remaining": max(0, retry_count - current_retries - 1),
            "degraded": action == "fallback_default",
            "fallback_value": self._get_node_fallback(node_id),
        }

    def _get_node_fallback(self, node_id: str) -> Any:
        """执行 _get_node_fallback 对应的逻辑，并返回处理结果。

        Args:
            node_id: str，调用方传入的 node_id 参数。

        Returns:
            Any，函数执行后的结果。
        """
        return {
            "result": None,
            "degraded": True,
            "fallback_reason": f"Node '{node_id}' failed after all retries",
        }

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    async def handle_dag_degradation(
        self,
        failed_ratio: float,
        total_nodes: int,
    ) -> dict:
        """处理输入事件或请求，并返回调用方需要的结果。

        Args:
            failed_ratio: float，调用方传入的 failed_ratio 参数。
            total_nodes: int，调用方传入的 total_nodes 参数。

        Returns:
            dict，函数执行后的结果。
        """
        async with self._lock:
            self._current_dag_failures = int(failed_ratio * total_nodes)
            self._current_dag_total = total_nodes

        threshold = 0.30
        if failed_ratio > threshold:
            action = "terminate"
            logger.warning(
                "DAG degradation: %.0f%% nodes failed (%d/%d) > %.0f%% threshold — "
                "early termination triggered",
                failed_ratio * 100,
                self._current_dag_failures,
                total_nodes,
                threshold * 100,
            )
        else:
            action = "continue"

        event = DegradationEvent(
            level=DegradationLevel.L3_DAG,
            timestamp=time.time(),
            description=(
                f"DAG failure ratio: {failed_ratio:.1%} "
                f"({self._current_dag_failures}/{total_nodes})"
            ),
            action_taken=action,
            affected_component="dag",
            span_attributes={"failed_ratio": failed_ratio, "total_nodes": total_nodes},
        )
        self._events.append(event)

        return {
            "action": action,
            "failed_count": self._current_dag_failures,
            "success_count": total_nodes - self._current_dag_failures,
            "should_terminate": failed_ratio > threshold,
        }

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    async def handle_system_failure(self) -> dict:
        """处理输入事件或请求，并返回调用方需要的结果。

        Returns:
            dict，函数执行后的结果。
        """
        async with self._lock:
            self._system_degraded = True

        event = DegradationEvent(
            level=DegradationLevel.L4_SYSTEM,
            timestamp=time.time(),
            description="System-wide cascading failure detected",
            action_taken="Global degradation mode + P0 alert",
            affected_component="system",
        )
        self._events.append(event)

        logger.critical(
            "P0 ALERT: System entering global degradation mode. "
            "All DAGs cancelled, preset responses enabled."
        )

        return {
            "action": "global_degradation",
            "p0_alert": True,
            "accept_new_requests": False,
            "preset_response": {
                "result": "Service temporarily degraded. Please retry later.",
                "degraded": True,
            },
        }

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    async def reset_dag_counters(self) -> None:
        """执行 reset_dag_counters 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            self._current_dag_failures = 0
            self._current_dag_total = 0
            self._node_retry_counts.clear()

    async def recover_system(self) -> None:
        """执行 recover_system 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        async with self._lock:
            self._system_degraded = False
            self._model_circuit_open.clear()
            self._model_calls.clear()
        logger.info("System recovered from global degradation mode")

    @property
    def is_system_degraded(self) -> bool:
        """执行 is_system_degraded 对应的逻辑，并返回处理结果。

        Returns:
            bool，函数执行后的结果。
        """
        return self._system_degraded

    def get_recent_events(self, count: int = 50) -> list[DegradationEvent]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            count: int，调用方传入的 count 参数。

        Returns:
            list[DegradationEvent]，函数执行后的结果。
        """
        return self._events[-count:]
