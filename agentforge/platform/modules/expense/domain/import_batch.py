"""导入批次模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ExpenseImportStatus(str, Enum):
    """报销导入状态枚举。"""

    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


class ExpenseImportItemStatus(str, Enum):
    """报销导入条目状态枚举。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExpenseImportItem(BaseModel):
    """报销导入条目相关组件。

    Attributes:
        filename: 字段值。
        attachment_id: 附件 ID。
        job_id: 任务ID。
        status: 当前状态。
        error: 错误信息。
    """

    model_config = ConfigDict(extra="forbid")

    filename: str
    attachment_id: str | None = None
    job_id: str | None = None
    status: ExpenseImportItemStatus
    error: str = ""


class ExpenseImportBatch(BaseModel):
    """报销导入批次相关组件。

    Attributes:
        batch_id: 批次ID。
        tenant_id: 租户 ID，用于数据隔离。
        status: 当前状态。
        total_files: 总计文件。
        success_count: 成功数量。
        failed_count: 失败数量。
        items: 条目。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    model_config = ConfigDict(extra="forbid")

    batch_id: str
    tenant_id: str
    status: ExpenseImportStatus
    total_files: int
    success_count: int
    failed_count: int
    items: list[ExpenseImportItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
