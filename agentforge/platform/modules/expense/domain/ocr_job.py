"""OCR任务模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class OcrJobStatus(str, Enum):
    """OCR任务状态枚举。"""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExpenseOcrJob(BaseModel):
    """报销OCR任务领域组件。

    Attributes:
        job_id: 任务ID。
        tenant_id: 租户 ID，用于数据隔离。
        attachment_id: 附件 ID。
        status: 当前状态。
        extraction_id: 提取ID。
        error: 错误信息。
        attempts: 字段值。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str
    tenant_id: str
    attachment_id: str
    status: OcrJobStatus = OcrJobStatus.QUEUED
    extraction_id: str | None = None
    error: str = ""
    attempts: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
