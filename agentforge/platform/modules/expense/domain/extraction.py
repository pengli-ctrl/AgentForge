"""提取模块。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ExpenseExtraction(BaseModel):
    """报销提取领域组件。

    Attributes:
        extraction_id: 提取ID。
        attachment_id: 附件 ID。
        amount_cents: 金额分。
        currency: 货币代码。
        expense_date: 报销。
        invoice_date: 发票。
        invoice_code: 发票代码。
        invoice_number: 发票。
        seller_tax_id: ID。
        buyer_tax_id: ID。
        applicant_id: ID。
        category: 字段值。
        description: 描述信息。
        raw_text: 文本。
        provider: 提供方。
        confidence: 字段值。
        requires_review: 要求审核。
    """

    model_config = ConfigDict(extra="forbid")

    extraction_id: str | None = None
    attachment_id: str | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    currency: str = "CNY"
    expense_date: date | None = None
    invoice_date: date | None = None
    invoice_code: str = ""
    invoice_number: str = ""
    seller_tax_id: str = ""
    buyer_tax_id: str = ""
    applicant_id: str | None = None
    category: str | None = None
    description: str = ""
    raw_text: str = ""
    provider: str = ""
    confidence: dict[str, float] = Field(default_factory=dict)
    requires_review: bool = True


class ExpenseExtractionRecord(BaseModel):
    """报销提取记录持久化模型。

    Attributes:
        extraction_id: 提取ID。
        tenant_id: 租户 ID，用于数据隔离。
        attachment_id: 附件 ID。
        extraction: 提取。
        created_at: 创建时间。
        consumed_at: 于。
    """

    extraction_id: str
    tenant_id: str
    attachment_id: str | None = None
    extraction: ExpenseExtraction
    created_at: datetime
    consumed_at: datetime | None = None
