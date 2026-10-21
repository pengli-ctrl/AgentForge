"""资产模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AssetStatus(str, Enum):
    """资产状态枚举。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


class Asset(BaseModel):
    """资产领域组件。

    Attributes:
        asset_id: 资产ID。
        tenant_id: 租户 ID，用于数据隔离。
        name: 名称。
        category: 字段值。
        status: 当前状态。
        created_by: 由。
        created_at: 创建时间。
        archived_at: 已归档于。
    """

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    tenant_id: str
    name: str
    category: str = "general"
    status: AssetStatus = AssetStatus.ACTIVE
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    archived_at: datetime | None = None


__all__ = ["Asset", "AssetStatus"]
