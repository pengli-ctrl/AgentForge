"""租户模块模型模块。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.db.models import utc_now


class TenantModuleRecord(Base):
    """租户模块记录持久化模型。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        module_name: 模块名称。
        enabled: 是否启用。
        plan_name: 套餐名称。
        config_version: 配置版本。
        source: 调用或事件来源。
        updated_by: 由。
        config_values: 配置值。
        secret_refs: 密钥。
        updated_at: 更新时间。
    """

    __tablename__ = "tenant_modules"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    module_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True)
    plan_name: Mapped[str] = mapped_column(String(64), default="")
    config_version: Mapped[int] = mapped_column(Integer(), default=1)
    source: Mapped[str] = mapped_column(String(32), default="tenant_override")
    updated_by: Mapped[str] = mapped_column(String(128), default="")
    config_values: Mapped[dict] = mapped_column(JSON, default=dict)
    secret_refs: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
