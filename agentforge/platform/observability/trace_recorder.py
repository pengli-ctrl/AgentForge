"""AgentForge 平台可观测性层：trace_recorder。

本模块负责 trace_recorder 相关的平台能力，是 平台可观测性层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：TraceRecord、TraceRecorder。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TraceRecord:
    """TraceRecord。

    TraceRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - trace_id: str。
    - tenant_id: str。
    - model: str。
    - provider: str。
    - input_tokens: int。
    - output_tokens: int。
    - cost_amount: float。
    - latency_ms: float。
    - status: str。
    - created_at: float。
    - error: str。
    - 方法 to_dict()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    trace_id: str
    tenant_id: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_amount: float = 0.0
    latency_ms: float = 0.0
    status: str = "ok"
    created_at: float = field(default_factory=time.time)
    error: str = ""

    def to_dict(self) -> dict:
        """执行 to_dict 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
        """
        return {
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "model": self.model,
            "provider": self.provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_amount": round(self.cost_amount, 6),
            "latency_ms": round(self.latency_ms, 2),
            "status": self.status,
            "created_at": self.created_at,
            "error": self.error,
        }


class TraceRecorder:
    """TraceRecorder。

    TraceRecorder 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 record()。
    - 方法 list_recent()。
    - 方法 summary()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, max_records: int = 5000) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            max_records: int，调用方传入的 max_records 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._records: list[TraceRecord] = []
        self._max_records = max_records

    def record(self, record: TraceRecord) -> None:
        """执行 record 对应的逻辑，并返回处理结果。

        Args:
            record: TraceRecord，调用方传入的 record 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._records.append(record)
        if len(self._records) > self._max_records:
            # FIFO 淘汰最旧，保持有界
            self._records = self._records[-self._max_records :]

    async def list_recent(
        self,
        tenant_id: str | None = None,
        limit: int = 50,
    ) -> list[TraceRecord]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[TraceRecord]，函数执行后的结果。
        """
        records = self._records
        if tenant_id:
            records = [r for r in records if r.tenant_id == tenant_id]
        # 新→旧
        records = list(reversed(records))
        return records[:limit]

    async def summary(self, tenant_id: str | None = None) -> dict:
        """执行 summary 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        records = self._records
        if tenant_id:
            records = [r for r in records if r.tenant_id == tenant_id]
        if not records:
            return {
                "tenant_id": tenant_id or "",
                "count": 0,
                "total_cost": 0.0,
                "total_latency_ms": 0.0,
                "avg_latency_ms": 0.0,
                "ok_rate": 0.0,
                "records": [],
            }
        total_cost = sum(r.cost_amount for r in records)
        total_latency = sum(r.latency_ms for r in records)
        ok = sum(1 for r in records if r.status == "ok")
        return {
            "tenant_id": tenant_id or "",
            "count": len(records),
            "total_cost": round(total_cost, 6),
            "total_latency_ms": round(total_latency, 2),
            "avg_latency_ms": round(total_latency / len(records), 2),
            "ok_rate": round(ok / len(records), 4),
            "records": [r.to_dict() for r in list(reversed(records))[:20]],
        }
