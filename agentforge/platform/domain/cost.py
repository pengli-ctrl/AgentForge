"""成本模块。"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class CostRecord(BaseModel):
    """成本记录持久化模型。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        task_id: 任务ID。
        model_name: 模型名称。
        provider: 提供方。
        input_tokens: 输入。
        output_tokens: 输出。
        amount: 金额。
        created_at: 创建时间。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    task_id: str
    model_name: str
    provider: str
    input_tokens: int
    output_tokens: int
    amount: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
