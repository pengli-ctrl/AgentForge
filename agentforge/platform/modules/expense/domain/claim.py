"""报销单模块。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExpenseClaimStatus(str, Enum):
    """报销单状态枚举。"""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    WAITING_APPROVAL = "waiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ExpenseClaim(BaseModel):
    """报销单相关组件。

    Attributes:
        claim_id: 报销单 ID。
        tenant_id: 租户 ID，用于数据隔离。
        applicant_id: ID。
        amount_cents: 金额分。
        currency: 货币代码。
        expense_date: 报销。
        category: 字段值。
        description: 描述信息。
        invoice_count: 发票数量。
        status: 当前状态。
        idempotency_key: 幂等键，用于避免重复处理。
        created_at: 创建时间。
        updated_at: 更新时间。
        metadata: 附加元数据。
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    tenant_id: str
    applicant_id: str
    amount_cents: int = Field(gt=0)
    currency: str = "CNY"
    expense_date: date
    category: str
    description: str = ""
    invoice_count: int = Field(default=0, ge=0)
    status: ExpenseClaimStatus = ExpenseClaimStatus.DRAFT
    idempotency_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def submit(self) -> None:
        """提交报销单。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if self.status != ExpenseClaimStatus.DRAFT:
            raise ValueError(f"cannot submit claim in status {self.status.value}")
        self.status = ExpenseClaimStatus.WAITING_APPROVAL
        self.updated_at = datetime.now(timezone.utc)

    def approve(self, approver_id: str, reason: str = "") -> None:
        """批准报销单。

        Args:
            approver_id: 审批人 ID。
            reason: 变更原因。
        """
        self._decide(ExpenseClaimStatus.APPROVED, approver_id, reason)

    def reject(self, approver_id: str, reason: str) -> None:
        """拒绝报销单。

        Args:
            approver_id: 审批人 ID。
            reason: 变更原因。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if not reason.strip():
            raise ValueError("rejection reason is required")
        self._decide(ExpenseClaimStatus.REJECTED, approver_id, reason)

    def _decide(
        self,
        status: ExpenseClaimStatus,
        approver_id: str,
        reason: str,
    ) -> None:
        """处理报销单。

        Args:
            status: 目标状态。
            approver_id: 审批人 ID。
            reason: 变更原因。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if self.status != ExpenseClaimStatus.WAITING_APPROVAL:
            raise ValueError(f"cannot decide claim in status {self.status.value}")
        if not approver_id.strip():
            raise ValueError("approver_id is required")
        self.status = status
        self.metadata = {
            **self.metadata,
            "approval": {
                "decision": status.value,
                "decided_by": approver_id,
                "reason": reason,
                "decided_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        self.updated_at = datetime.now(timezone.utc)
