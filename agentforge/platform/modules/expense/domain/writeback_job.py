"""写回任务模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.modules.expense.domain.ledger import ExpenseWritebackItem


class ExpenseWritebackJobStatus(str, Enum):
    """报销写回任务状态枚举。"""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


class ExpenseWritebackJob(BaseModel):
    """报销写回任务领域组件。

    Attributes:
        job_id: 任务ID。
        tenant_id: 租户 ID，用于数据隔离。
        connector_id: 连接器ID。
        action: 操作。
        actor_id: 执行操作的参与者 ID。
        claim_ids: 报销单。
        status: 当前状态。
        total_claims: 总计报销单。
        succeeded_claims: 报销单。
        failed_claims: 失败报销单。
        skipped_claims: 报销单。
        attempts: 字段值。
        error: 错误信息。
        items: 条目。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str
    tenant_id: str
    connector_id: str
    action: str
    actor_id: str
    claim_ids: list[str] = Field(default_factory=list)
    status: ExpenseWritebackJobStatus = ExpenseWritebackJobStatus.QUEUED
    total_claims: int = 0
    succeeded_claims: int = 0
    failed_claims: int = 0
    skipped_claims: int = 0
    attempts: int = 0
    error: str = ""
    items: list[ExpenseWritebackItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
