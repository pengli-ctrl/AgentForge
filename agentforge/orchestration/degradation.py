"""降级模块。"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

CIRCUIT_WINDOW_CALLS = 10
CIRCUIT_FAILURE_THRESHOLD = 0.5
CIRCUIT_OPEN_DURATION_SECONDS = 900
MAX_TRACKED_OUTCOMES = 20


class DegradationLevel(Enum):
    """降级级别状态枚举。"""

    L1_MODEL = 1
    L2_NODE = 2  # 节点级降级。
    L3_DAG = 3
    L4_SYSTEM = 4


@dataclass
class DegradationEvent:
    """降级事件相关组件。

    Attributes:
        level: 级别。
        timestamp: 字段值。
        description: 描述信息。
        action_taken: 操作。
        affected_component: 字段值。
        span_attributes: 链路片段。
    """

    level: DegradationLevel
    timestamp: float
    description: str
    action_taken: str
    affected_component: str
    span_attributes: dict = field(default_factory=dict)


class DegradationManager:
    """降级相关组件。"""

    def __init__(self):
        """初始化 DegradationManager。"""
        self._lock = asyncio.Lock()
        self._model_calls: dict[str, list[bool]] = {}
        self._model_circuit_open: dict[str, float] = {}
        # 失败重试。
        self._node_retry_counts: dict[str, int] = {}
        self._current_dag_failures: int = 0
        self._current_dag_total: int = 0
        self._system_degraded: bool = False
        self._events: list[DegradationEvent] = []

    async def handle_llm_failure(self, model_name: str, error: Exception) -> dict:
        """处理LLM失败。

        Args:
            model_name: 模型名称。
            error: 错误。

        Returns:
            结构化结果字典。
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
        """记录LLM成功。

        Args:
            model_name: 模型名称。
        """
        async with self._lock:
            self._record_outcome_locked(model_name, True)

    def _record_outcome_locked(self, model_name: str, success: bool) -> None:
        """记录结果。

        Args:
            model_name: 模型名称。
            success: 成功。
        """
        outcomes = self._model_calls.setdefault(model_name, [])
        outcomes.append(success)
        if len(outcomes) > MAX_TRACKED_OUTCOMES:
            del outcomes[:-MAX_TRACKED_OUTCOMES]

    def _maybe_open_circuit(self, model_name: str, now: float) -> None:
        """在满足条件时打开熔断器。

        Args:
            model_name: 模型名称。
            now: 输入参数。
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
        """获取降级。

        Args:
            failed_model: 失败模型。

        Returns:
            结果列表。
        """
        # 成本统计。
        all_models = ["Qwen3-Pro", "GLM-5", "DeepSeek-V3", "Kimi", "MiniMax"]
        now = time.time()
        available = [
            m for m in all_models if m != failed_model and self._model_circuit_open.get(m, 0) < now
        ]
        return available

    async def handle_node_failure(
        self,
        node_id: str,
        error: Exception,
        retry_count: int = 2,
    ) -> dict:
        """处理节点失败。

        Args:
            node_id: 节点 ID。
            error: 错误。
            retry_count: 重试数量。

        Returns:
            结构化结果字典。
        """
        async with self._lock:
            current_retries = self._node_retry_counts.get(node_id, 0)

            if current_retries < retry_count:
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
        """获取节点。

        Args:
            node_id: 节点 ID。

        Returns:
            处理结果对象。
        """
        return {
            "result": None,
            "degraded": True,
            "fallback_reason": f"Node '{node_id}' failed after all retries",
        }

    async def handle_dag_degradation(
        self,
        failed_ratio: float,
        total_nodes: int,
    ) -> dict:
        """处理DAG降级。

        Args:
            failed_ratio: 失败。
            total_nodes: 总计。

        Returns:
            结构化结果字典。
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

    async def handle_system_failure(self) -> dict:
        """处理系统失败。

        Returns:
            结构化结果字典。
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

    async def reset_dag_counters(self) -> None:
        """重置 DAG 运行计数器。"""
        async with self._lock:
            self._current_dag_failures = 0
            self._current_dag_total = 0
            self._node_retry_counts.clear()

    async def recover_system(self) -> None:
        """处理系统。"""
        async with self._lock:
            self._system_degraded = False
            self._model_circuit_open.clear()
            self._model_calls.clear()
        logger.info("System recovered from global degradation mode")

    @property
    def is_system_degraded(self) -> bool:
        """判断系统是否处于降级状态。

        Returns:
            操作是否成功。
        """
        return self._system_degraded

    def get_recent_events(self, count: int = 50) -> list[DegradationEvent]:
        """获取最近事件。

        Args:
            count: 数量。

        Returns:
            结果列表。
        """
        return self._events[-count:]
