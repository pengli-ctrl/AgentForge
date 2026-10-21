"""发票模块。"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExpenseInvoiceStatus(str, Enum):
    """报销发票状态枚举。"""

    ACTIVE = "active"
    RELEASED = "released"


class ExpenseInvoiceVerificationStatus(str, Enum):
    """报销发票核验状态枚举。"""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    MISMATCH = "mismatch"
    INVALID = "invalid"
    FAILED = "failed"


class ExpenseInvoiceEnforcementMode(str, Enum):
    """报销发票模式枚举。"""

    OFF = "off"
    DUPLICATE_ONLY = "duplicate_only"
    VERIFIED = "verified"
    STRICT = "strict"


class ExpenseInvoice(BaseModel):
    """报销发票领域组件。

    Attributes:
        invoice_id: 发票 ID。
        tenant_id: 租户 ID，用于数据隔离。
        claim_id: 报销单 ID。
        duplicate_key: 重复键。
        fingerprint: 指纹。
        invoice_code: 发票代码。
        invoice_number: 发票。
        invoice_date: 发票。
        amount_cents: 金额分。
        currency: 货币代码。
        seller_tax_id: ID。
        buyer_tax_id: ID。
        status: 当前状态。
        verification_status: 核验状态。
        verification_provider: 核验提供方。
        verification_ref: 核验引用。
        verification_message: 核验。
        verified_at: 已验证于。
        released_at: 已释放于。
        release_reason: 释放原因。
        metadata: 附加元数据。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    tenant_id: str
    claim_id: str
    duplicate_key: str | None
    fingerprint: str
    invoice_code: str = ""
    invoice_number: str
    invoice_date: date
    amount_cents: int = Field(gt=0)
    currency: str = "CNY"
    seller_tax_id: str = ""
    buyer_tax_id: str = ""
    status: ExpenseInvoiceStatus = ExpenseInvoiceStatus.ACTIVE
    verification_status: ExpenseInvoiceVerificationStatus = (
        ExpenseInvoiceVerificationStatus.UNVERIFIED
    )
    verification_provider: str = ""
    verification_ref: str = ""
    verification_message: str = ""
    verified_at: datetime | None = None
    released_at: datetime | None = None
    release_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InvoiceDuplicateMatch(BaseModel):
    """发票重复匹配相关组件。

    Attributes:
        invoice_id: 发票 ID。
        claim_id: 报销单 ID。
        fingerprint: 指纹。
        invoice_number: 发票。
        amount_cents: 金额分。
    """

    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    claim_id: str
    fingerprint: str
    invoice_number: str
    amount_cents: int


class InvoiceDuplicateCheckItem(BaseModel):
    """发票重复检查条目相关组件。

    Attributes:
        index: 索引。
        fingerprint: 指纹。
        duplicate: 重复。
        match: 匹配。
    """

    model_config = ConfigDict(extra="forbid")

    index: int
    fingerprint: str
    duplicate: bool
    match: InvoiceDuplicateMatch | None = None


class InvoiceDuplicateCheckResult(BaseModel):
    """发票重复检查结果相关组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        duplicates_found: 字段值。
        items: 条目。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    duplicates_found: int
    items: list[InvoiceDuplicateCheckItem] = Field(default_factory=list)


class InvoiceVerificationResult(BaseModel):
    """发票核验结果领域组件。

    Attributes:
        invoice_id: 发票 ID。
        claim_id: 报销单 ID。
        status: 当前状态。
        provider: 提供方。
        verification_ref: 核验引用。
        message: 消息内容。
        verified_at: 已验证于。
    """

    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    claim_id: str
    status: ExpenseInvoiceVerificationStatus
    provider: str = ""
    verification_ref: str = ""
    message: str = ""
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InvoiceReadiness(BaseModel):
    """发票就绪状态相关组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        claim_id: 报销单 ID。
        mode: 模式。
        ready: 字段值。
        reasons: 字段值。
        active_invoices: 活跃发票。
        verified_invoices: 已验证发票。
        total_invoice_amount_cents: 总计发票金额分。
        registration_status: 注册状态。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    claim_id: str
    mode: ExpenseInvoiceEnforcementMode
    ready: bool
    reasons: list[str] = Field(default_factory=list)
    active_invoices: int = 0
    verified_invoices: int = 0
    total_invoice_amount_cents: int = 0
    registration_status: str = ""


class InvoiceGateAlert(BaseModel):
    """发票门禁告警领域组件。

    Attributes:
        type: 资源类型。
        severity: 严重性。
        message: 消息内容。
        value: 值。
        claim_id: 报销单 ID。
        actor_id: 执行操作的参与者 ID。
        anchor: 字段值。
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    severity: str
    message: str
    value: float
    claim_id: str = ""
    actor_id: str = ""
    anchor: str = ""


class InvoiceGateAlertStateStatus(str, Enum):
    """发票门禁告警状态枚举。"""

    ACTIVE = "active"
    RESOLVED = "resolved"


class InvoiceGateAlertState(BaseModel):
    """发票门禁告警状态相关组件。

    Attributes:
        alert_id: 告警ID。
        tenant_id: 租户 ID，用于数据隔离。
        alert_key: 告警键。
        type: 资源类型。
        severity: 严重性。
        message: 消息内容。
        value: 值。
        claim_id: 报销单 ID。
        actor_id: 执行操作的参与者 ID。
        occurrence: 字段值。
        status: 当前状态。
        created_at: 创建时间。
        updated_at: 更新时间。
        resolved_at: 于。
    """

    model_config = ConfigDict(extra="forbid")

    alert_id: str
    tenant_id: str
    alert_key: str
    type: str
    severity: str
    message: str
    value: float
    claim_id: str = ""
    actor_id: str = ""
    occurrence: int = 1
    status: InvoiceGateAlertStateStatus = InvoiceGateAlertStateStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None

    def resolve(self, resolved_at: datetime | None = None) -> None:
        """解析发票门禁告警状态。

        Args:
            resolved_at: 已解决时间。
        """
        if self.status == InvoiceGateAlertStateStatus.RESOLVED:
            return
        timestamp = resolved_at or datetime.now(timezone.utc)
        self.status = InvoiceGateAlertStateStatus.RESOLVED
        self.resolved_at = timestamp
        self.updated_at = timestamp


class InvoiceGateSummary(BaseModel):
    """发票门禁摘要领域组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        claims_with_readiness: 报销单使用就绪状态。
        ready_claims: 报销单。
        not_ready_claims: 不报销单。
        override_claims: 覆盖报销单。
        blocked_attempts: 阻塞。
        reason_counts: 原因。
        last_blocked_at: 阻塞于。
        oldest_blocked_at: 阻塞于。
        oldest_blocked_age_seconds: 阻塞。
        override_actors: 覆盖。
        alerts: 告警。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    claims_with_readiness: int
    ready_claims: int
    not_ready_claims: int
    override_claims: int
    blocked_attempts: int
    reason_counts: dict[str, int] = Field(default_factory=dict)
    last_blocked_at: str = ""
    oldest_blocked_at: str = ""
    oldest_blocked_age_seconds: float = 0.0
    override_actors: dict[str, int] = Field(default_factory=dict)
    alerts: list[InvoiceGateAlert] = Field(default_factory=list)


def normalize_invoice_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """规范化发票载荷。

    Args:
        payload: 事件、工作流或请求载荷。

    Returns:
        结构化结果字典。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    if not isinstance(payload, dict):
        raise ValueError("invoice must be an object")
    invoice_number = _required_text(payload.get("invoice_number"), "invoice_number")
    invoice_code = _optional_text(payload.get("invoice_code")).upper()
    seller_tax_id = _optional_text(payload.get("seller_tax_id")).upper()
    buyer_tax_id = _optional_text(payload.get("buyer_tax_id")).upper()
    currency = (_optional_text(payload.get("currency")) or "CNY").upper()
    amount_cents = payload.get("amount_cents")
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
        raise ValueError("amount_cents must be a positive integer")
    raw_date = payload.get("invoice_date")
    if isinstance(raw_date, date):
        invoice_date = raw_date
    elif isinstance(raw_date, str) and raw_date.strip():
        try:
            invoice_date = date.fromisoformat(raw_date.strip())
        except ValueError as exc:
            raise ValueError("invoice_date must use YYYY-MM-DD") from exc
    else:
        raise ValueError("invoice_date is required")
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("invoice metadata must be an object")
    return {
        "invoice_code": invoice_code,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date.isoformat(),
        "amount_cents": amount_cents,
        "currency": currency,
        "seller_tax_id": seller_tax_id,
        "buyer_tax_id": buyer_tax_id,
        "metadata": dict(metadata),
    }


def invoice_fingerprint(payload: dict[str, Any]) -> str:
    """计算发票内容指纹。

    Args:
        payload: 事件、工作流或请求载荷。

    Returns:
        字符串结果。
    """
    normalized = normalize_invoice_payload(payload)
    canonical = {
        "invoice_code": normalized["invoice_code"],
        "invoice_number": normalized["invoice_number"],
        "invoice_date": normalized["invoice_date"],
        "amount_cents": normalized["amount_cents"],
        "currency": normalized["currency"],
        "seller_tax_id": normalized["seller_tax_id"],
    }
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _required_text(value: object, field: str) -> str:
    """读取并校验必填文本字段。

    Args:
        value: 待处理值。
        field: 字段。

    Returns:
        字符串结果。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object) -> str:
    """读取可选文本字段。

    Args:
        value: 待处理值。

    Returns:
        字符串结果。
    """
    return value.strip() if isinstance(value, str) else ""
