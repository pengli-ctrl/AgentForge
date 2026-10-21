"""租户账户模型模块。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.db.models import utc_now


class TenantAccountRecord(Base):
    """租户账户记录持久化模型。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        name: 名称。
        plan_name: 套餐名称。
        status: 当前状态。
        created_at: 创建时间。
        updated_at: 更新时间。
        suspended_at: 于。
        cancelled_at: 于。
        status_reason: 状态原因。
    """

    __tablename__ = "tenant_accounts"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    plan_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_reason: Mapped[str] = mapped_column(String(512), default="")
