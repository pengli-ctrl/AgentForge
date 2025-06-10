"""Prometheus 指标定义 — 任务数、Agent 执行耗时、LLM 调用次数等。

用于全链路可观测性（Layer 4 容错防线）。
指标通过 /metrics 端点以 Prometheus 格式暴露。

核心指标：
- agentforge_tasks_total：任务总数（按状态分）
- agentforge_agent_duration_seconds：Agent 执行耗时直方图
- agentforge_llm_calls_total：LLM 调用次数
- agentforge_tool_calls_total：工具调用次数（按工具名和成功/失败分）
- agentforge_event_bus_throughput：事件总线吞吐量
- agentforge_circuit_breaker_state：熔断器状态
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Prometheus 指标收集器 — 定义和记录所有业务指标。

    当 prometheus_client 不可用时，使用内存计数器作为回退方案。

    指标定义遵循 Prometheus 最佳实践：
    - Counter：单调递增的计数器（任务总数、LLM 调用次数）
    - Histogram：分布统计（Agent 执行耗时）
    - Gauge：可增可减的仪表盘（活跃任务数、熔断器状态）

    Args:
        namespace: 指标命名空间（默认 "agentforge"）。
    """

    def __init__(self, namespace: str = "agentforge") -> None:
        self.namespace = namespace
        self._prometheus: Any = None
        self._metrics: dict[str, Any] = {}
        self._init_prometheus()

    def _init_prometheus(self) -> None:
        """初始化 Prometheus 指标定义。"""
        try:
            from prometheus_client import (
                Counter,
                Gauge,
                Histogram,
            )

            self._prometheus = True

            self._metrics["tasks_total"] = Counter(
                f"{self.namespace}_tasks_total",
                "Total number of tasks by status",
                ["status", "workflow"],
            )

            self._metrics["agent_duration"] = Histogram(
                f"{self.namespace}_agent_duration_seconds",
                "Agent execution duration in seconds",
                ["agent_name", "status"],
                buckets=(
                    0.1,
                    0.25,
                    0.5,
                    1.0,
                    2.5,
                    5.0,
                    10.0,
                    30.0,
                    60.0,
                    120.0,
                ),
            )

            self._metrics["llm_calls_total"] = Counter(
                f"{self.namespace}_llm_calls_total",
                "Total LLM API calls",
                ["agent_name", "status"],
            )

            self._metrics["tool_calls_total"] = Counter(
                f"{self.namespace}_tool_calls_total",
                "Total tool calls by tool name and result",
                ["tool_name", "agent_name", "status"],
            )

            self._metrics["event_bus_throughput"] = Counter(
                f"{self.namespace}_event_bus_throughput",
                "Event bus throughput (events published)",
                ["event_type"],
            )

            self._metrics["active_tasks"] = Gauge(
                f"{self.namespace}_active_tasks",
                "Number of currently active tasks",
            )

            self._metrics["circuit_breaker_state"] = Gauge(
                f"{self.namespace}_circuit_breaker_state",
                "Circuit breaker state (0=closed, 1=open, 2=half-open)",
                ["agent_name"],
            )

            self._metrics["retry_count"] = Counter(
                f"{self.namespace}_retry_count",
                "Total retry attempts",
                ["agent_name", "reason"],
            )

            logger.info("Prometheus metrics initialized (namespace=%s)", self.namespace)
        except ImportError:
            logger.warning("prometheus_client not installed, using in-memory counters")
            self._prometheus = None
            self._fallback: dict[str, dict[str, float]] = {}

    def record_task(self, status: str, workflow: str = "") -> None:
        """记录任务状态变更。

        Args:
            status: 任务状态（pending/running/completed/failed/cancelled）。
            workflow: 工作流名称。
        """
        if self._prometheus:
            self._metrics["tasks_total"].labels(status=status, workflow=workflow).inc()
        else:
            key = f"tasks_{status}_{workflow}"
            self._fallback[key] = self._fallback.get(key, 0) + 1

    def record_agent_duration(
        self, agent_name: str, duration: float, status: str = "success"
    ) -> None:
        """记录 Agent 执行耗时。

        Args:
            agent_name: Agent 名称。
            duration: 执行耗时（秒）。
            status: 执行状态（success/error/timeout）。
        """
        if self._prometheus:
            self._metrics["agent_duration"].labels(agent_name=agent_name, status=status).observe(
                duration
            )
        else:
            key = f"agent_duration_{agent_name}_{status}"
            if key not in self._fallback:
                self._fallback[key] = 0.0
            self._fallback[key] += duration

    def record_llm_call(self, agent_name: str, status: str = "success") -> None:
        """记录 LLM 调用。

        Args:
            agent_name: 调用 LLM 的 Agent 名称。
            status: 调用状态（success/error/timeout）。
        """
        if self._prometheus:
            self._metrics["llm_calls_total"].labels(agent_name=agent_name, status=status).inc()
        else:
            key = f"llm_calls_{agent_name}_{status}"
            self._fallback[key] = self._fallback.get(key, 0) + 1

    def record_tool_call(self, tool_name: str, agent_name: str, status: str = "success") -> None:
        """记录工具调用。

        Args:
            tool_name: 工具名称。
            agent_name: 调用工具的 Agent 名称。
            status: 调用状态（success/error）。
        """
        if self._prometheus:
            self._metrics["tool_calls_total"].labels(
                tool_name=tool_name, agent_name=agent_name, status=status
            ).inc()
        else:
            key = f"tool_calls_{tool_name}_{agent_name}_{status}"
            self._fallback[key] = self._fallback.get(key, 0) + 1

    def record_event_published(self, event_type: str) -> None:
        """记录事件总线上的事件发布。

        Args:
            event_type: 事件类型。
        """
        if self._prometheus:
            self._metrics["event_bus_throughput"].labels(event_type=event_type).inc()
        else:
            key = f"event_bus_{event_type}"
            self._fallback[key] = self._fallback.get(key, 0) + 1

    def set_active_tasks(self, count: int) -> None:
        """设置当前活跃任务数。

        Args:
            count: 活跃任务数。
        """
        if self._prometheus:
            self._metrics["active_tasks"].set(count)
        else:
            self._fallback["active_tasks"] = float(count)

    def set_circuit_breaker(self, agent_name: str, state: int) -> None:
        """设置熔断器状态。

        Args:
            agent_name: Agent 名称。
            state: 熔断器状态（0=closed, 1=open, 2=half-open）。
        """
        if self._prometheus:
            self._metrics["circuit_breaker_state"].labels(agent_name=agent_name).set(state)
        else:
            self._fallback[f"circuit_breaker_{agent_name}"] = float(state)

    def record_retry(self, agent_name: str, reason: str = "timeout") -> None:
        """记录重试。

        Args:
            agent_name: Agent 名称。
            reason: 重试原因（timeout/error）。
        """
        if self._prometheus:
            self._metrics["retry_count"].labels(agent_name=agent_name, reason=reason).inc()
        else:
            key = f"retry_{agent_name}_{reason}"
            self._fallback[key] = self._fallback.get(key, 0) + 1

    def generate_metrics(self) -> str:
        """生成 Prometheus 格式的指标文本。

        用于 /metrics 端点暴露。

        Returns:
            Prometheus 格式的指标文本。
        """
        if self._prometheus:
            from prometheus_client import generate_latest

            return generate_latest().decode("utf-8")

        # 回退方案：生成简单文本格式
        lines: list[str] = []
        for key, value in sorted(self._fallback.items()):
            lines.append(f"# TYPE {key} counter")
            lines.append(f"{key} {value}")
        return "\n".join(lines) + "\n"


# 全局单例
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """获取全局 MetricsCollector 单例。

    Returns:
        全局 MetricsCollector 实例。
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
