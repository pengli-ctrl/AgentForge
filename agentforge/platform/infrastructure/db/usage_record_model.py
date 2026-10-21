"""用量记录模型模块。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.db.models import utc_now


class UsageRecordModel(Base):
    """用量记录模型持久化模型。

    Attributes:
        record_id: 记录ID。
        tenant_id: 租户 ID，用于数据隔离。
        metric: 用量指标。
        quantity: 本次记录的用量数量。
        source: 调用或事件来源。
        idempotency_key: 幂等键，用于避免重复处理。
        occurred_at: 用量发生时间。
        payload: 事件、工作流或请求载荷。
    """

    __tablename__ = "usage_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_usage_tenant_idempotency"),
    )

    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    metric: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(Integer())
    source: Mapped[str] = mapped_column(String(128), default="platform")
    idempotency_key: Mapped[str] = mapped_column(String(128))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
