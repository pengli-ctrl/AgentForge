"""台账模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ExpenseWritebackStatus(str, Enum):
    """报销写回状态枚举。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    COMPENSATED = "compensated"


class ExpenseVerificationStatus(str, Enum):
    """报销核验状态枚举。"""

    VERIFIED = "verified"
    NOT_FOUND = "not_found"
    MISMATCH = "mismatch"
    FAILED = "failed"


class ExpenseCompensationStatus(str, Enum):
    """报销补偿状态枚举。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExpenseWritebackItem(BaseModel):
    """报销写回条目相关组件。

    Attributes:
        claim_id: 报销单 ID。
        status: 当前状态。
        external_id: 外部ID。
        error: 错误信息。
        idempotent_replay: 幂等。
        attempted_at: 于。
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    status: ExpenseWritebackStatus
    external_id: str = ""
    error: str = ""
    idempotent_replay: bool = False
    attempted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExpenseWritebackBatch(BaseModel):
    """报销写回批次相关组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        connector_id: 连接器ID。
        action: 操作。
        total: 总计。
        succeeded: 字段值。
        failed: 失败。
        skipped: 字段值。
        items: 条目。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    connector_id: str
    action: str
    total: int
    succeeded: int
    failed: int
    skipped: int
    items: list[ExpenseWritebackItem] = Field(default_factory=list)


class ExpenseVerificationItem(BaseModel):
    """报销核验条目相关组件。

    Attributes:
        claim_id: 报销单 ID。
        status: 当前状态。
        expected_external_id: 外部ID。
        external_id: 外部ID。
        external_amount_cents: 外部金额分。
        message: 消息内容。
        checked_at: 于。
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    status: ExpenseVerificationStatus
    expected_external_id: str = ""
    external_id: str = ""
    external_amount_cents: int | None = None
    message: str = ""
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExpenseVerificationBatch(BaseModel):
    """报销核验批次相关组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        connector_id: 连接器ID。
        lookup_action: 操作。
        total: 总计。
        verified: 已验证。
        not_found: 不。
        mismatch: 不一致。
        failed: 失败。
        items: 条目。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    connector_id: str
    lookup_action: str
    total: int
    verified: int
    not_found: int
    mismatch: int
    failed: int
    items: list[ExpenseVerificationItem] = Field(default_factory=list)


class ExpenseCompensationItem(BaseModel):
    """报销补偿条目相关组件。

    Attributes:
        claim_id: 报销单 ID。
        status: 当前状态。
        external_id: 外部ID。
        compensation_id: 补偿ID。
        error: 错误信息。
        compensated_at: 于。
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    status: ExpenseCompensationStatus
    external_id: str = ""
    compensation_id: str = ""
    error: str = ""
    compensated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExpenseCompensationBatch(BaseModel):
    """报销补偿批次相关组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        connector_id: 连接器ID。
        compensation_action: 补偿操作。
        total: 总计。
        succeeded: 字段值。
        failed: 失败。
        skipped: 字段值。
        items: 条目。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    connector_id: str
    compensation_action: str
    total: int
    succeeded: int
    failed: int
    skipped: int
    items: list[ExpenseCompensationItem] = Field(default_factory=list)


class ExpenseReconciliationIssue(BaseModel):
    """报销对账相关组件。

    Attributes:
        claim_id: 报销单 ID。
        amount_cents: 金额分。
        status: 当前状态。
        connector_id: 连接器ID。
        error: 错误信息。
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    amount_cents: int
    status: str
    connector_id: str = ""
    error: str = ""


class ExpenseLedgerReconciliation(BaseModel):
    """报销台账对账相关组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        total_claims: 总计报销单。
        total_amount_cents: 总计金额分。
        written_claims: 报销单。
        written_amount_cents: 金额分。
        failed_claims: 失败报销单。
        failed_amount_cents: 失败金额分。
        compensated_claims: 报销单。
        compensated_amount_cents: 金额分。
        pending_claims: 待处理报销单。
        pending_amount_cents: 待处理金额分。
        issues: 字段值。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    total_claims: int
    total_amount_cents: int
    written_claims: int
    written_amount_cents: int
    failed_claims: int
    failed_amount_cents: int
    compensated_claims: int
    compensated_amount_cents: int
    pending_claims: int
    pending_amount_cents: int
    issues: list[ExpenseReconciliationIssue] = Field(default_factory=list)
