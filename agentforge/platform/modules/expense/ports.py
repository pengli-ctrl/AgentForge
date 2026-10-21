"""端口模块。"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from agentforge.platform.modules.expense.domain.attachment import ExpenseAttachment
from agentforge.platform.modules.expense.domain.claim import ExpenseClaim, ExpenseClaimStatus
from agentforge.platform.modules.expense.domain.extraction import ExpenseExtractionRecord
from agentforge.platform.modules.expense.domain.import_batch import ExpenseImportBatch
from agentforge.platform.modules.expense.domain.invoice import ExpenseInvoice, InvoiceGateAlertState
from agentforge.platform.modules.expense.domain.ocr_job import ExpenseOcrJob
from agentforge.platform.modules.expense.domain.writeback_job import ExpenseWritebackJob


class ExpenseClaimRepository(Protocol):
    """报销单仓储，负责持久化读写。"""

    async def save(self, claim: ExpenseClaim) -> None:
        """保存报销单。

        Args:
            claim: 报销单对象。
        """
        ...

    async def get(self, tenant_id: str, claim_id: str) -> ExpenseClaim | None:
        """获取报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。

        Returns:
            报销报销单无结果。
        """
        ...

    async def get_by_idempotency_key(
        self, tenant_id: str, idempotency_key: str
    ) -> ExpenseClaim | None:
        """获取由键。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            idempotency_key: 幂等键，用于避免重复处理。

        Returns:
            报销报销单无结果。
        """
        ...

    async def list_page(
        self,
        tenant_id: str,
        *,
        status: ExpenseClaimStatus | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[ExpenseClaim], str | None]:
        """查询页面。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结果元组。
        """
        ...

    async def list_all(
        self,
        tenant_id: str,
        *,
        status: ExpenseClaimStatus | None = None,
        limit: int = 10_000,
    ) -> list[ExpenseClaim]:
        """查询全部。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...

    async def list_tenants(self) -> list[str]:
        """查询租户。

        Returns:
            结果列表。
        """
        ...

    async def sum_amount_cents(
        self,
        tenant_id: str,
        statuses: set[ExpenseClaimStatus],
        date_from: date,
        date_to: date,
    ) -> int:
        """汇总报销金额分值。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            statuses: 输入参数。
            date_from: 从。
            date_to: 到。

        Returns:
            整数结果。
        """
        ...


class ExpenseAttachmentRepository(Protocol):
    """报销附件仓储，负责持久化读写。"""

    async def save(self, attachment: ExpenseAttachment) -> None:
        """保存报销附件。

        Args:
            attachment: 附件。
        """
        ...

    async def get(self, tenant_id: str, attachment_id: str) -> ExpenseAttachment | None:
        """读取报销附件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_id: 附件 ID。

        Returns:
            报销附件无结果。
        """
        ...

    async def list_by_ids(
        self, tenant_id: str, attachment_ids: list[str]
    ) -> list[ExpenseAttachment]:
        """查询由。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_ids: 附件 ID 列表。

        Returns:
            结果列表。
        """
        ...


class ExpenseExtractionRepository(Protocol):
    """报销提取仓储，负责持久化读写。"""

    async def save(self, record: ExpenseExtractionRecord) -> None:
        """保存报销提取。

        Args:
            record: 待处理的领域记录。
        """
        ...

    async def get(self, tenant_id: str, extraction_id: str) -> ExpenseExtractionRecord | None:
        """读取报销提取。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            extraction_id: 提取 ID。

        Returns:
            报销提取记录无结果。
        """
        ...


class ExpenseOcrJobRepository(Protocol):
    """报销OCR任务仓储，负责持久化读写。"""

    async def save(self, job: ExpenseOcrJob) -> None:
        """保存报销OCR任务。

        Args:
            job: 后台任务对象。
        """
        ...

    async def get(self, tenant_id: str, job_id: str) -> ExpenseOcrJob | None:
        """读取报销OCR任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销OCR任务无结果。
        """
        ...

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseOcrJob]:
        """查询报销OCR任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...


class ExpenseImportBatchRepository(Protocol):
    """报销导入批次仓储，负责持久化读写。"""

    async def save(self, batch: ExpenseImportBatch) -> None:
        """保存报销导入批次。

        Args:
            batch: 批次。
        """
        ...

    async def get(self, tenant_id: str, batch_id: str) -> ExpenseImportBatch | None:
        """获取报销导入批次。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            batch_id: 批次 ID。

        Returns:
            报销导入批次无结果。
        """
        ...

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseImportBatch]:
        """查询报销导入批次。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...


class ExpenseWritebackJobRepository(Protocol):
    """报销写回任务仓储，负责持久化读写。"""

    async def save(self, job: ExpenseWritebackJob) -> None:
        """保存报销写回任务。

        Args:
            job: 后台任务对象。
        """
        ...

    async def get(self, tenant_id: str, job_id: str) -> ExpenseWritebackJob | None:
        """读取报销写回任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销写回任务无结果。
        """
        ...

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseWritebackJob]:
        """查询报销写回任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...


class ExpenseInvoiceRepository(Protocol):
    """报销发票仓储，负责持久化读写。"""

    async def save(self, invoice: ExpenseInvoice) -> None:
        """保存报销发票。

        Args:
            invoice: 发票对象。
        """
        ...

    async def get(self, tenant_id: str, invoice_id: str) -> ExpenseInvoice | None:
        """读取报销发票。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            invoice_id: 发票 ID。

        Returns:
            报销发票无结果。
        """
        ...

    async def get_active_by_fingerprint(
        self,
        tenant_id: str,
        fingerprint: str,
    ) -> ExpenseInvoice | None:
        """获取活跃由指纹。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            fingerprint: 指纹。

        Returns:
            报销发票无结果。
        """
        ...

    async def list_by_claim(self, tenant_id: str, claim_id: str) -> list[ExpenseInvoice]:
        """查询由报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。

        Returns:
            结果列表。
        """
        ...

    async def list(self, tenant_id: str, limit: int = 200) -> list[ExpenseInvoice]:
        """查询报销发票。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...


class ExpenseInvoiceGateAlertRepository(Protocol):
    """报销发票门禁告警仓储，负责持久化读写。"""

    async def save(self, alert: InvoiceGateAlertState) -> None:
        """保存报销发票门禁告警。

        Args:
            alert: 告警。
        """
        ...

    async def get(self, tenant_id: str, alert_id: str) -> InvoiceGateAlertState | None:
        """读取报销发票门禁告警。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            alert_id: 告警 ID。

        Returns:
            发票门禁告警状态无结果。
        """
        ...

    async def find_active(
        self,
        tenant_id: str,
        alert_key: str,
    ) -> InvoiceGateAlertState | None:
        """查找活跃。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            alert_key: 告警键。

        Returns:
            发票门禁告警状态无结果。
        """
        ...

    async def list_active(self, tenant_id: str) -> list[InvoiceGateAlertState]:
        """查询活跃。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        ...

    async def count_occurrences(self, tenant_id: str, alert_key: str) -> int:
        """统计报销发票门禁告警。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            alert_key: 告警键。

        Returns:
            整数结果。
        """
        ...

    async def list_all(
        self,
        tenant_id: str,
        limit: int = 10_000,
    ) -> list[InvoiceGateAlertState]:
        """查询全部。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...

    async def list_tenants(self) -> list[str]:
        """查询租户。

        Returns:
            结果列表。
        """
        ...
