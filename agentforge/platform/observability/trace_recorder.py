"""链路记录器模块。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TraceRecord:
    """链路记录持久化模型。

    Attributes:
        trace_id: 链路ID。
        tenant_id: 租户 ID，用于数据隔离。
        model: 模型。
        provider: 提供方。
        input_tokens: 输入。
        output_tokens: 输出。
        cost_amount: 成本金额。
        latency_ms: 延迟，单位为毫秒。
        status: 当前状态。
        created_at: 创建时间。
        error: 错误信息。
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
        """处理到字典。

        Returns:
            结构化结果字典。
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
    """链路记录器相关组件。"""

    def __init__(self, max_records: int = 5000) -> None:
        """初始化 TraceRecorder。

        Args:
            max_records: 最大记录。
        """
        self._records: list[TraceRecord] = []
        self._max_records = max_records

    def record(self, record: TraceRecord) -> None:
        """记录链路记录器。

        Args:
            record: 待处理的领域记录。
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
        """查询最近。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        records = self._records
        if tenant_id:
            records = [r for r in records if r.tenant_id == tenant_id]
        # 新→旧
        records = list(reversed(records))
        return records[:limit]

    async def summary(self, tenant_id: str | None = None) -> dict:
        """处理摘要。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
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
