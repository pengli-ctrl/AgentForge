"""附件模块。"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class ExpenseAttachment(BaseModel):
    """报销附件领域组件。

    Attributes:
        attachment_id: 附件 ID。
        tenant_id: 租户 ID，用于数据隔离。
        claim_id: 报销单 ID。
        filename: 字段值。
        content_type: 内容。
        size_bytes: 大小。
        sha256: 字段值。
        object_key: 对象键。
        created_at: 创建时间。
    """

    model_config = ConfigDict(extra="forbid")

    attachment_id: str
    tenant_id: str
    claim_id: str | None = None
    filename: str
    content_type: str
    size_bytes: int = Field(ge=0)
    sha256: str
    object_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
