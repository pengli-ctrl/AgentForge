"""指标暴露接口 — Prometheus 格式的指标暴露。

API 端点：
    GET /metrics — Prometheus 格式的指标数据
"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.observability.metrics import MetricsCollector, get_metrics_collector

logger = logging.getLogger(__name__)


class MetricsRoutes:
    """指标暴露路由处理器。

    封装 Prometheus 指标的 HTTP 暴露逻辑。

    Args:
        metrics: MetricsCollector 实例（不传则使用全局单例）。
    """

    def __init__(self, metrics: MetricsCollector | None = None) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            metrics: MetricsCollector | None，调用方传入的 metrics 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.metrics = metrics or get_metrics_collector()

    async def get_metrics(self) -> str:
        """获取 Prometheus 格式的指标数据。

        Returns:
            Prometheus 格式的指标文本。
        """
        return self.metrics.generate_metrics()

    async def get_metrics_info(self) -> dict[str, Any]:
        """获取指标信息摘要。

        Returns:
            包含指标名称和描述的字典。
        """
        return {
            "metrics_endpoint": "/metrics",
            "format": "prometheus",
            "description": "AgentForge Prometheus metrics endpoint",
            "available_metrics": [
                {
                    "name": "agentforge_tasks_total",
                    "type": "counter",
                    "description": "Total number of tasks by status",
                    "labels": ["status", "workflow"],
                },
                {
                    "name": "agentforge_agent_duration_seconds",
                    "type": "histogram",
                    "description": "Agent execution duration in seconds",
                    "labels": ["agent_name", "status"],
                },
                {
                    "name": "agentforge_llm_calls_total",
                    "type": "counter",
                    "description": "Total LLM API calls",
                    "labels": ["agent_name", "status"],
                },
                {
                    "name": "agentforge_tool_calls_total",
                    "type": "counter",
                    "description": "Total tool calls by tool name and result",
                    "labels": ["tool_name", "agent_name", "status"],
                },
                {
                    "name": "agentforge_event_bus_throughput",
                    "type": "counter",
                    "description": "Event bus throughput (events published)",
                    "labels": ["event_type"],
                },
                {
                    "name": "agentforge_active_tasks",
                    "type": "gauge",
                    "description": "Number of currently active tasks",
                    "labels": [],
                },
                {
                    "name": "agentforge_circuit_breaker_state",
                    "type": "gauge",
                    "description": "Circuit breaker state (0=closed, 1=open, 2=half-open)",
                    "labels": ["agent_name"],
                },
            ],
        }
