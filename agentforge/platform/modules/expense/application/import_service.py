"""导入服务模块。"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
from uuid import uuid4

from agentforge.platform.modules.expense.application.attachment_service import (
    ExpenseAttachmentService,
)
from agentforge.platform.modules.expense.application.ocr_job_service import ExpenseOcrJobService
from agentforge.platform.modules.expense.domain.import_batch import (
    ExpenseImportBatch,
    ExpenseImportItem,
    ExpenseImportItemStatus,
    ExpenseImportStatus,
)
from agentforge.platform.modules.expense.domain.ocr_job import OcrJobStatus
from agentforge.platform.modules.expense.ports import ExpenseImportBatchRepository


class ExpenseImportService:
    """报销导入应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        repository: ExpenseImportBatchRepository,
        attachments: ExpenseAttachmentService,
        jobs: ExpenseOcrJobService | None,
    ) -> None:
        """初始化 ExpenseImportService。

        Args:
            repository: 数据仓储实现。
            attachments: 输入参数。
            jobs: 任务。
        """
        self._repository = repository
        self._attachments = attachments
        self._jobs = jobs

    async def create_batch(self, tenant_id: str, files: list[dict]) -> ExpenseImportBatch:
        """创建批次。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            files: 文件。

        Returns:
            报销导入批次结果。
        """
        items: list[ExpenseImportItem] = []
        for file in files:
            filename = str(file.get("filename") or "")
            try:
                attachment = await self._attachments.upload(
                    tenant_id=tenant_id,
                    filename=filename,
                    content_type=str(file.get("content_type") or ""),
                    data=_decode_base64(file.get("content_base64")),
                )
                job_id = None
                item_status = ExpenseImportItemStatus.SUCCEEDED
                error = ""
                if self._jobs is not None:
                    job = await self._jobs.enqueue(tenant_id, attachment.attachment_id)
                    job_id = job.job_id
                    if job.status == OcrJobStatus.FAILED:
                        item_status = ExpenseImportItemStatus.FAILED
                        error = job.error
                items.append(
                    ExpenseImportItem(
                        filename=filename,
                        attachment_id=attachment.attachment_id,
                        job_id=job_id,
                        status=item_status,
                        error=error,
                    )
                )
            except (ValueError, binascii.Error, RuntimeError) as exc:
                items.append(
                    ExpenseImportItem(
                        filename=filename,
                        status=ExpenseImportItemStatus.FAILED,
                        error=str(exc)[:500],
                    )
                )
        batch = _build_batch(tenant_id, items)
        await self._repository.save(batch)
        return batch

    async def get(self, tenant_id: str, batch_id: str) -> ExpenseImportBatch:
        """读取报销导入。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            batch_id: 批次 ID。

        Returns:
            报销导入批次结果。

        Raises:
            LookupError: 操作无法完成时抛出。
        """
        batch = await self._repository.get(tenant_id, batch_id)
        if batch is None:
            raise LookupError("import batch not found")
        return batch

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseImportBatch]:
        """查询报销导入。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        return await self._repository.list(tenant_id, limit=limit)

    async def retry_failed(self, tenant_id: str, batch_id: str) -> ExpenseImportBatch:
        """重试失败。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            batch_id: 批次 ID。

        Returns:
            报销导入批次结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        batch = await self.get(tenant_id, batch_id)
        if self._jobs is None:
            raise ValueError("OCR jobs are not configured")
        for index, item in enumerate(batch.items):
            if item.status != ExpenseImportItemStatus.FAILED or item.attachment_id is None:
                continue
            try:
                if item.job_id is None:
                    job = await self._jobs.enqueue(tenant_id, item.attachment_id)
                else:
                    job = await self._jobs.retry(tenant_id, item.job_id)
                batch.items[index] = item.model_copy(
                    update={
                        "job_id": job.job_id,
                        "status": ExpenseImportItemStatus.SUCCEEDED,
                        "error": "",
                    }
                )
            except (LookupError, ValueError) as exc:
                batch.items[index] = item.model_copy(update={"error": str(exc)[:500]})
        refreshed = _build_batch(
            tenant_id,
            batch.items,
            batch_id=batch.batch_id,
            created_at=batch.created_at,
        )
        await self._repository.save(refreshed)
        return refreshed


def _build_batch(
    tenant_id: str,
    items: list[ExpenseImportItem],
    *,
    batch_id: str | None = None,
    created_at: datetime | None = None,
) -> ExpenseImportBatch:
    """构建批次。

    Args:
        tenant_id: 租户 ID，用于数据隔离。
        items: 待处理条目列表。
        batch_id: 批次 ID。
        created_at: 创建时间。

    Returns:
        报销导入批次结果。
    """
    failed = sum(item.status == ExpenseImportItemStatus.FAILED for item in items)
    success = len(items) - failed
    status = (
        ExpenseImportStatus.COMPLETED
        if failed == 0
        else ExpenseImportStatus.PARTIAL_FAILED if success else ExpenseImportStatus.FAILED
    )
    return ExpenseImportBatch(
        batch_id=batch_id or str(uuid4()),
        tenant_id=tenant_id,
        status=status,
        total_files=len(items),
        success_count=success,
        failed_count=failed,
        items=items,
        created_at=created_at or datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _decode_base64(value: object) -> bytes:
    """解码 Base64 数据。

    Args:
        value: 待处理值。

    Returns:
        处理结果对象。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    if not isinstance(value, str) or not value:
        raise ValueError("content_base64 is required")
    return base64.b64decode(value, validate=True)
