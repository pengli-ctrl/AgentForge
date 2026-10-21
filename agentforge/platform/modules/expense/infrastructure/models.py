"""数据模型模块。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.db.models import utc_now
from agentforge.platform.modules.expense.domain.attachment import ExpenseAttachment
from agentforge.platform.modules.expense.domain.claim import ExpenseClaim, ExpenseClaimStatus
from agentforge.platform.modules.expense.domain.extraction import (
    ExpenseExtraction,
    ExpenseExtractionRecord,
)
from agentforge.platform.modules.expense.domain.import_batch import (
    ExpenseImportBatch,
    ExpenseImportItem,
    ExpenseImportStatus,
)
from agentforge.platform.modules.expense.domain.invoice import (
    ExpenseInvoice,
    ExpenseInvoiceStatus,
    ExpenseInvoiceVerificationStatus,
    InvoiceGateAlertState,
    InvoiceGateAlertStateStatus,
)
from agentforge.platform.modules.expense.domain.ledger import ExpenseWritebackItem
from agentforge.platform.modules.expense.domain.ocr_job import ExpenseOcrJob, OcrJobStatus
from agentforge.platform.modules.expense.domain.writeback_job import (
    ExpenseWritebackJob,
    ExpenseWritebackJobStatus,
)


class ExpenseClaimRecord(Base):
    """报销单记录相关组件。

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
        payload: 事件、工作流或请求载荷。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    __tablename__ = "expense_claims"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_expense_claims_tenant_idempotency",
        ),
    )

    claim_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    applicant_id: Mapped[str] = mapped_column(String(64), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer())
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    expense_date: Mapped[date] = mapped_column(Date())
    category: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text(), default="")
    invoice_count: Mapped[int] = mapped_column(Integer(), default=0)
    status: Mapped[str] = mapped_column(String(32), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, claim: ExpenseClaim) -> "ExpenseClaimRecord":
        """将持久化记录转换为领域对象。

        Args:
            claim: 报销单对象。

        Returns:
            报销单结果。
        """
        return cls(
            claim_id=claim.claim_id,
            tenant_id=claim.tenant_id,
            applicant_id=claim.applicant_id,
            amount_cents=claim.amount_cents,
            currency=claim.currency,
            expense_date=claim.expense_date,
            category=claim.category,
            description=claim.description,
            invoice_count=claim.invoice_count,
            status=claim.status.value,
            idempotency_key=claim.idempotency_key,
            payload=claim.metadata,
            created_at=claim.created_at,
            updated_at=claim.updated_at,
        )

    def apply_domain(self, claim: ExpenseClaim) -> None:
        """应用领域。

        Args:
            claim: 报销单对象。
        """
        self.amount_cents = claim.amount_cents
        self.currency = claim.currency
        self.expense_date = claim.expense_date
        self.category = claim.category
        self.description = claim.description
        self.invoice_count = claim.invoice_count
        self.status = claim.status.value
        self.payload = claim.metadata
        self.updated_at = claim.updated_at

    def to_domain(self) -> ExpenseClaim:
        """转换领域。

        Returns:
            报销报销单结果。
        """
        return ExpenseClaim(
            claim_id=self.claim_id,
            tenant_id=self.tenant_id,
            applicant_id=self.applicant_id,
            amount_cents=self.amount_cents,
            currency=self.currency,
            expense_date=self.expense_date,
            category=self.category,
            description=self.description,
            invoice_count=self.invoice_count,
            status=ExpenseClaimStatus(self.status),
            idempotency_key=self.idempotency_key,
            metadata=self.payload or {},
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ExpenseAttachmentRecord(Base):
    """报销附件记录持久化模型。

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

    __tablename__ = "expense_attachments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "object_key",
            name="uq_expense_attachments_tenant_object_key",
        ),
    )

    attachment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    claim_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer())
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    object_key: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, attachment: ExpenseAttachment) -> "ExpenseAttachmentRecord":
        """将持久化记录转换为领域对象。

        Args:
            attachment: 附件。

        Returns:
            附件结果。
        """
        return cls(
            attachment_id=attachment.attachment_id,
            tenant_id=attachment.tenant_id,
            claim_id=attachment.claim_id,
            filename=attachment.filename,
            content_type=attachment.content_type,
            size_bytes=attachment.size_bytes,
            sha256=attachment.sha256,
            object_key=attachment.object_key,
            created_at=attachment.created_at,
        )

    def apply_domain(self, attachment: ExpenseAttachment) -> None:
        """应用领域。

        Args:
            attachment: 附件。
        """
        self.claim_id = attachment.claim_id
        self.filename = attachment.filename
        self.content_type = attachment.content_type
        self.size_bytes = attachment.size_bytes
        self.sha256 = attachment.sha256

    def to_domain(self) -> ExpenseAttachment:
        """转换领域。

        Returns:
            报销附件结果。
        """
        return ExpenseAttachment(
            attachment_id=self.attachment_id,
            tenant_id=self.tenant_id,
            claim_id=self.claim_id,
            filename=self.filename,
            content_type=self.content_type,
            size_bytes=self.size_bytes,
            sha256=self.sha256,
            object_key=self.object_key,
            created_at=self.created_at,
        )


class ExpenseExtractionRecordModel(Base):
    """报销提取记录模型持久化模型。

    Attributes:
        extraction_id: 提取ID。
        tenant_id: 租户 ID，用于数据隔离。
        attachment_id: 附件 ID。
        payload: 事件、工作流或请求载荷。
        created_at: 创建时间。
        consumed_at: 于。
    """

    __tablename__ = "expense_extractions"

    extraction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    attachment_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @classmethod
    def from_domain(cls, record: ExpenseExtractionRecord) -> "ExpenseExtractionRecordModel":
        """将持久化记录转换为领域对象。

        Args:
            record: 待处理的领域记录。

        Returns:
            提取记录结果。
        """
        return cls(
            extraction_id=record.extraction_id,
            tenant_id=record.tenant_id,
            attachment_id=record.attachment_id,
            payload=record.extraction.model_dump(mode="json"),
            created_at=record.created_at,
            consumed_at=record.consumed_at,
        )

    def apply_domain(self, record: ExpenseExtractionRecord) -> None:
        """应用领域。

        Args:
            record: 待处理的领域记录。
        """
        self.attachment_id = record.attachment_id
        self.payload = record.extraction.model_dump(mode="json")
        self.consumed_at = record.consumed_at

    def to_domain(self) -> ExpenseExtractionRecord:
        """转换领域。

        Returns:
            报销提取记录结果。
        """
        return ExpenseExtractionRecord(
            extraction_id=self.extraction_id,
            tenant_id=self.tenant_id,
            attachment_id=self.attachment_id,
            extraction=ExpenseExtraction.model_validate(self.payload),
            created_at=self.created_at,
            consumed_at=self.consumed_at,
        )


class ExpenseOcrJobRecord(Base):
    """报销OCR任务记录持久化模型。

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

    __tablename__ = "expense_ocr_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    attachment_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    extraction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str] = mapped_column(Text(), default="")
    attempts: Mapped[int] = mapped_column(Integer(), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, job: ExpenseOcrJob) -> "ExpenseOcrJobRecord":
        """将持久化记录转换为领域对象。

        Args:
            job: 后台任务对象。

        Returns:
            OCR任务结果。
        """
        return cls(
            job_id=job.job_id,
            tenant_id=job.tenant_id,
            attachment_id=job.attachment_id,
            status=job.status.value,
            extraction_id=job.extraction_id,
            error=job.error,
            attempts=job.attempts,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    def apply_domain(self, job: ExpenseOcrJob) -> None:
        """应用领域。

        Args:
            job: 后台任务对象。
        """
        self.status = job.status.value
        self.extraction_id = job.extraction_id
        self.error = job.error
        self.attempts = job.attempts
        self.updated_at = job.updated_at

    def to_domain(self) -> ExpenseOcrJob:
        """转换领域。

        Returns:
            报销OCR任务结果。
        """
        return ExpenseOcrJob(
            job_id=self.job_id,
            tenant_id=self.tenant_id,
            attachment_id=self.attachment_id,
            status=OcrJobStatus(self.status),
            extraction_id=self.extraction_id,
            error=self.error,
            attempts=self.attempts,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ExpenseImportBatchRecord(Base):
    """报销导入批次记录相关组件。

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

    __tablename__ = "expense_import_batches"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    total_files: Mapped[int] = mapped_column(Integer())
    success_count: Mapped[int] = mapped_column(Integer())
    failed_count: Mapped[int] = mapped_column(Integer())
    items: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, batch: ExpenseImportBatch) -> "ExpenseImportBatchRecord":
        """将持久化记录转换为领域对象。

        Args:
            batch: 批次。

        Returns:
            导入批次结果。
        """
        return cls(
            batch_id=batch.batch_id,
            tenant_id=batch.tenant_id,
            status=batch.status.value,
            total_files=batch.total_files,
            success_count=batch.success_count,
            failed_count=batch.failed_count,
            items=[item.model_dump(mode="json") for item in batch.items],
            created_at=batch.created_at,
            updated_at=batch.updated_at,
        )

    def apply_domain(self, batch: ExpenseImportBatch) -> None:
        """应用领域。

        Args:
            batch: 批次。
        """
        self.status = batch.status.value
        self.total_files = batch.total_files
        self.success_count = batch.success_count
        self.failed_count = batch.failed_count
        self.items = [item.model_dump(mode="json") for item in batch.items]
        self.updated_at = batch.updated_at

    def to_domain(self) -> ExpenseImportBatch:
        """转换领域。

        Returns:
            报销导入批次结果。
        """
        return ExpenseImportBatch(
            batch_id=self.batch_id,
            tenant_id=self.tenant_id,
            status=ExpenseImportStatus(self.status),
            total_files=self.total_files,
            success_count=self.success_count,
            failed_count=self.failed_count,
            items=[ExpenseImportItem.model_validate(item) for item in self.items or []],
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ExpenseWritebackJobRecord(Base):
    """报销写回任务记录持久化模型。

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

    __tablename__ = "expense_writeback_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    connector_id: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(128))
    actor_id: Mapped[str] = mapped_column(String(128))
    claim_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), index=True)
    total_claims: Mapped[int] = mapped_column(Integer(), default=0)
    succeeded_claims: Mapped[int] = mapped_column(Integer(), default=0)
    failed_claims: Mapped[int] = mapped_column(Integer(), default=0)
    skipped_claims: Mapped[int] = mapped_column(Integer(), default=0)
    attempts: Mapped[int] = mapped_column(Integer(), default=0)
    error: Mapped[str] = mapped_column(Text(), default="")
    items: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, job: ExpenseWritebackJob) -> "ExpenseWritebackJobRecord":
        """将持久化记录转换为领域对象。

        Args:
            job: 后台任务对象。

        Returns:
            写回任务结果。
        """
        return cls(
            job_id=job.job_id,
            tenant_id=job.tenant_id,
            connector_id=job.connector_id,
            action=job.action,
            actor_id=job.actor_id,
            claim_ids=list(job.claim_ids),
            status=job.status.value,
            total_claims=job.total_claims,
            succeeded_claims=job.succeeded_claims,
            failed_claims=job.failed_claims,
            skipped_claims=job.skipped_claims,
            attempts=job.attempts,
            error=job.error,
            items=[item.model_dump(mode="json") for item in job.items],
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    def apply_domain(self, job: ExpenseWritebackJob) -> None:
        """应用领域。

        Args:
            job: 后台任务对象。
        """
        self.status = job.status.value
        self.total_claims = job.total_claims
        self.succeeded_claims = job.succeeded_claims
        self.failed_claims = job.failed_claims
        self.skipped_claims = job.skipped_claims
        self.attempts = job.attempts
        self.error = job.error
        self.items = [item.model_dump(mode="json") for item in job.items]
        self.updated_at = job.updated_at

    def to_domain(self) -> ExpenseWritebackJob:
        """转换领域。

        Returns:
            报销写回任务结果。
        """
        return ExpenseWritebackJob(
            job_id=self.job_id,
            tenant_id=self.tenant_id,
            connector_id=self.connector_id,
            action=self.action,
            actor_id=self.actor_id,
            claim_ids=list(self.claim_ids or []),
            status=ExpenseWritebackJobStatus(self.status),
            total_claims=self.total_claims,
            succeeded_claims=self.succeeded_claims,
            failed_claims=self.failed_claims,
            skipped_claims=self.skipped_claims,
            attempts=self.attempts,
            error=self.error,
            items=[ExpenseWritebackItem.model_validate(item) for item in self.items or []],
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ExpenseInvoiceRecord(Base):
    """报销发票记录持久化模型。

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
        payload: 事件、工作流或请求载荷。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    __tablename__ = "expense_invoices"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "duplicate_key",
            name="uq_expense_invoices_tenant_duplicate_key",
        ),
    )

    invoice_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    claim_id: Mapped[str] = mapped_column(String(64), index=True)
    duplicate_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    invoice_code: Mapped[str] = mapped_column(String(64), default="")
    invoice_number: Mapped[str] = mapped_column(String(128), index=True)
    invoice_date: Mapped[date] = mapped_column(Date())
    amount_cents: Mapped[int] = mapped_column(Integer())
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    seller_tax_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    buyer_tax_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), index=True)
    verification_status: Mapped[str] = mapped_column(String(32), index=True)
    verification_provider: Mapped[str] = mapped_column(String(128), default="")
    verification_ref: Mapped[str] = mapped_column(String(128), default="")
    verification_message: Mapped[str] = mapped_column(Text(), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_reason: Mapped[str] = mapped_column(Text(), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, invoice: ExpenseInvoice) -> "ExpenseInvoiceRecord":
        """将持久化记录转换为领域对象。

        Args:
            invoice: 发票对象。

        Returns:
            发票结果。
        """
        return cls(
            invoice_id=invoice.invoice_id,
            tenant_id=invoice.tenant_id,
            claim_id=invoice.claim_id,
            duplicate_key=invoice.duplicate_key,
            fingerprint=invoice.fingerprint,
            invoice_code=invoice.invoice_code,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            amount_cents=invoice.amount_cents,
            currency=invoice.currency,
            seller_tax_id=invoice.seller_tax_id,
            buyer_tax_id=invoice.buyer_tax_id,
            status=invoice.status.value,
            verification_status=invoice.verification_status.value,
            verification_provider=invoice.verification_provider,
            verification_ref=invoice.verification_ref,
            verification_message=invoice.verification_message,
            verified_at=invoice.verified_at,
            released_at=invoice.released_at,
            release_reason=invoice.release_reason,
            payload=invoice.metadata,
            created_at=invoice.created_at,
            updated_at=invoice.updated_at,
        )

    def apply_domain(self, invoice: ExpenseInvoice) -> None:
        """应用领域。

        Args:
            invoice: 发票对象。
        """
        self.duplicate_key = invoice.duplicate_key
        self.status = invoice.status.value
        self.verification_status = invoice.verification_status.value
        self.verification_provider = invoice.verification_provider
        self.verification_ref = invoice.verification_ref
        self.verification_message = invoice.verification_message
        self.verified_at = invoice.verified_at
        self.released_at = invoice.released_at
        self.release_reason = invoice.release_reason
        self.payload = invoice.metadata
        self.updated_at = invoice.updated_at

    def to_domain(self) -> ExpenseInvoice:
        """转换领域。

        Returns:
            报销发票结果。
        """
        return ExpenseInvoice(
            invoice_id=self.invoice_id,
            tenant_id=self.tenant_id,
            claim_id=self.claim_id,
            duplicate_key=self.duplicate_key,
            fingerprint=self.fingerprint,
            invoice_code=self.invoice_code,
            invoice_number=self.invoice_number,
            invoice_date=self.invoice_date,
            amount_cents=self.amount_cents,
            currency=self.currency,
            seller_tax_id=self.seller_tax_id,
            buyer_tax_id=self.buyer_tax_id,
            status=ExpenseInvoiceStatus(self.status),
            verification_status=ExpenseInvoiceVerificationStatus(self.verification_status),
            verification_provider=self.verification_provider,
            verification_ref=self.verification_ref,
            verification_message=self.verification_message,
            verified_at=self.verified_at,
            released_at=self.released_at,
            release_reason=self.release_reason,
            metadata=self.payload or {},
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ExpenseInvoiceGateAlertRecord(Base):
    """报销发票门禁告警记录持久化模型。

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

    __tablename__ = "expense_invoice_gate_alerts"
    __table_args__ = (
        Index(
            "uq_expense_invoice_gate_alerts_active_key",
            "tenant_id",
            "alert_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    alert_key: Mapped[str] = mapped_column(Text())
    type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    message: Mapped[str] = mapped_column(Text(), default="")
    value: Mapped[float] = mapped_column(Float(), default=0.0)
    claim_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    actor_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    occurrence: Mapped[int] = mapped_column(Integer(), default=1)
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @classmethod
    def from_domain(cls, alert: InvoiceGateAlertState) -> "ExpenseInvoiceGateAlertRecord":
        """将持久化记录转换为领域对象。

        Args:
            alert: 告警。

        Returns:
            发票门禁告警结果。
        """
        return cls(
            alert_id=alert.alert_id,
            tenant_id=alert.tenant_id,
            alert_key=alert.alert_key,
            type=alert.type,
            severity=alert.severity,
            message=alert.message,
            value=alert.value,
            claim_id=alert.claim_id,
            actor_id=alert.actor_id,
            occurrence=alert.occurrence,
            status=alert.status.value,
            created_at=alert.created_at,
            updated_at=alert.updated_at,
            resolved_at=alert.resolved_at,
        )

    def apply_domain(self, alert: InvoiceGateAlertState) -> None:
        """应用领域。

        Args:
            alert: 告警。
        """
        self.alert_key = alert.alert_key
        self.type = alert.type
        self.severity = alert.severity
        self.message = alert.message
        self.value = alert.value
        self.claim_id = alert.claim_id
        self.actor_id = alert.actor_id
        self.occurrence = alert.occurrence
        self.status = alert.status.value
        self.updated_at = alert.updated_at
        self.resolved_at = alert.resolved_at

    def to_domain(self) -> InvoiceGateAlertState:
        """转换领域。

        Returns:
            发票门禁告警状态结果。
        """
        return InvoiceGateAlertState(
            alert_id=self.alert_id,
            tenant_id=self.tenant_id,
            alert_key=self.alert_key,
            type=self.type,
            severity=self.severity,
            message=self.message,
            value=self.value,
            claim_id=self.claim_id,
            actor_id=self.actor_id,
            occurrence=self.occurrence,
            status=InvoiceGateAlertStateStatus(self.status),
            created_at=self.created_at,
            updated_at=self.updated_at,
            resolved_at=self.resolved_at,
        )
