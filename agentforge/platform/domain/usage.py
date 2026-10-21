"""用量模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class UsageMetric(str, Enum):
    """用量指标枚举。"""

    OCR_PAGES = "ocr_pages"
    MODEL_TOKENS = "model_tokens"
    WORKFLOW_EXECUTIONS = "workflow_executions"
    STORAGE_BYTES = "storage_bytes"
    NOTIFICATION_COUNT = "notification_count"


class UsageRecord(BaseModel):
    """用量记录持久化模型。

    Attributes:
        record_id: 记录ID。
        tenant_id: 租户 ID，用于数据隔离。
        metric: 用量指标。
        quantity: 本次记录的用量数量。
        source: 调用或事件来源。
        idempotency_key: 幂等键，用于避免重复处理。
        occurred_at: 用量发生时间。
        metadata: 附加元数据。
    """

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    metric: UsageMetric
    quantity: int = Field(gt=0)
    source: str = "platform"
    idempotency_key: str = ""
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class UsageDecision(BaseModel):
    """用量决策领域组件。

    Attributes:
        accepted: 字段值。
        blocked: 阻塞。
        metric: 用量指标。
        used: 已使用。
        limit: 返回记录的最大数量。
        overage: 字段值。
        policy: 策略。
        record_id: 记录ID。
        duplicate: 重复。
    """

    accepted: bool
    blocked: bool
    metric: UsageMetric
    used: int
    limit: int
    overage: int
    policy: str
    record_id: str = ""
    duplicate: bool = False


class UsageAlert(BaseModel):
    """用量告警领域组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        metric: 用量指标。
        status: 当前状态。
        used: 已使用。
        limit: 返回记录的最大数量。
        ratio: 字段值。
    """

    tenant_id: str
    metric: UsageMetric
    status: str
    used: int
    limit: int
    ratio: float


class InvoiceLine(BaseModel):
    """发票相关组件。

    Attributes:
        metric: 用量指标。
        quantity: 本次记录的用量数量。
        unit_price_cents: 分。
        amount_cents: 金额分。
    """

    metric: UsageMetric
    quantity: int
    unit_price_cents: float
    amount_cents: int


class TenantInvoice(BaseModel):
    """租户发票领域组件。

    Attributes:
        invoice_id: 发票 ID。
        tenant_id: 租户 ID，用于数据隔离。
        plan_name: 套餐名称。
        period_start: 账单周期开始时间。
        period_end: 账单周期结束时间。
        currency: 货币代码。
        base_fee_cents: 基础分。
        lines: 字段值。
        total_cents: 总计分。
        generated_at: 于。
    """

    invoice_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    plan_name: str
    period_start: datetime
    period_end: datetime
    currency: str = "CNY"
    base_fee_cents: int = 0
    lines: list[InvoiceLine] = Field(default_factory=list)
    total_cents: int = 0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = [
    "InvoiceLine",
    "TenantInvoice",
    "UsageAlert",
    "UsageDecision",
    "UsageMetric",
    "UsageRecord",
]
