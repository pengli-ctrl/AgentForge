"""OCR任务服务模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agentforge.platform.modules.expense.application.attachment_service import (
    ExpenseAttachmentService,
)
from agentforge.platform.modules.expense.application.ocr_extraction_service import ExpenseOcrService
from agentforge.platform.modules.expense.domain.ocr_job import ExpenseOcrJob, OcrJobStatus
from agentforge.platform.modules.expense.ports import ExpenseOcrJobRepository
from agentforge.platform.sdk.ports import WorkflowClientPort


class ExpenseOcrJobService:
    """报销OCR任务应用服务，编排领域用例及其副作用。"""

    task_queue = "expense-copilot"

    def __init__(
        self,
        repository: ExpenseOcrJobRepository,
        attachments: ExpenseAttachmentService,
        ocr: ExpenseOcrService,
        workflow_client: WorkflowClientPort | None = None,
    ) -> None:
        """初始化 ExpenseOcrJobService。

        Args:
            repository: 数据仓储实现。
            attachments: 输入参数。
            ocr: OCR。
            workflow_client: 工作流客户端。
        """
        self._repository = repository
        self._attachments = attachments
        self._ocr = ocr
        self._workflow_client = workflow_client

    async def enqueue(self, tenant_id: str, attachment_id: str) -> ExpenseOcrJob:
        """写入队列报销OCR任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_id: 附件 ID。

        Returns:
            报销OCR任务结果。

        Raises:
            LookupError: 操作无法完成时抛出。
        """
        attachment = await self._attachments.get(tenant_id, attachment_id)
        if attachment is None:
            raise LookupError("attachment not found")
        job = ExpenseOcrJob(
            job_id=str(uuid4()),
            tenant_id=tenant_id,
            attachment_id=attachment_id,
        )
        await self._repository.save(job)
        await self._dispatch(job)
        return await self.get(tenant_id, job.job_id)

    async def enqueue_batch(self, tenant_id: str, attachment_ids: list[str]) -> list[ExpenseOcrJob]:
        """加入队列批次。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_ids: 附件 ID 列表。

        Returns:
            结果列表。
        """
        return [await self.enqueue(tenant_id, attachment_id) for attachment_id in attachment_ids]

    async def get(self, tenant_id: str, job_id: str) -> ExpenseOcrJob:
        """读取报销OCR任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销OCR任务结果。

        Raises:
            LookupError: 操作无法完成时抛出。
        """
        job = await self._repository.get(tenant_id, job_id)
        if job is None:
            raise LookupError("OCR job not found")
        return job

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseOcrJob]:
        """查询报销OCR任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        return await self._repository.list(tenant_id, limit=limit)

    async def summary(self, tenant_id: str) -> dict[str, object]:
        """汇总报销OCR任务信息。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        jobs = await self._repository.list(tenant_id, limit=10000)
        counts = {status.value: 0 for status in OcrJobStatus}
        for job in jobs:
            counts[job.status.value] += 1
        total = len(jobs)
        succeeded = counts[OcrJobStatus.SUCCEEDED.value]
        return {
            "tenant_id": tenant_id,
            "total": total,
            "by_status": counts,
            "success_rate": round(succeeded / total, 4) if total else 0.0,
            "total_attempts": sum(job.attempts for job in jobs),
        }

    async def process(self, tenant_id: str, job_id: str) -> ExpenseOcrJob:
        """处理报销OCR任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销OCR任务结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        job = await self.get(tenant_id, job_id)
        if job.status == OcrJobStatus.SUCCEEDED:
            return job
        job.status = OcrJobStatus.RUNNING
        job.attempts += 1
        job.error = ""
        job.updated_at = datetime.now(timezone.utc)
        await self._repository.save(job)
        try:
            attachment = await self._attachments.get(job.tenant_id, job.attachment_id)
            if attachment is None:
                raise ValueError("attachment not found")
            metadata, _ = attachment
            content = await self._attachments.get_content(job.tenant_id, job.attachment_id)
            if content is None:
                raise ValueError("attachment content not found")
            extraction = await self._ocr.extract(
                job.tenant_id,
                content,
                metadata.content_type,
                metadata.attachment_id,
            )
            job.status = OcrJobStatus.SUCCEEDED
            job.extraction_id = extraction.extraction_id
        except Exception as exc:  # noqa: BLE001 - persisted for operator retry
            job.status = OcrJobStatus.FAILED
            job.error = str(exc)[:1000]
        job.updated_at = datetime.now(timezone.utc)
        await self._repository.save(job)
        return job

    async def retry(self, tenant_id: str, job_id: str) -> ExpenseOcrJob:
        """重试报销OCR任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销OCR任务结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        job = await self.get(tenant_id, job_id)
        if job.status != OcrJobStatus.FAILED:
            raise ValueError("only failed OCR jobs can be retried")
        job.status = OcrJobStatus.QUEUED
        job.error = ""
        job.updated_at = datetime.now(timezone.utc)
        await self._repository.save(job)
        await self._dispatch(job)
        return await self.get(tenant_id, job.job_id)

    async def _dispatch(self, job: ExpenseOcrJob) -> None:
        """分发报销OCR任务。

        Args:
            job: 后台任务对象。
        """
        if self._workflow_client is None:
            await self.process(job.tenant_id, job.job_id)
            return
        from agentforge.platform.modules.expense.workflows.ocr_job import ExpenseOcrWorkflow

        await self._workflow_client.start_workflow(
            ExpenseOcrWorkflow.run,
            {"tenant_id": job.tenant_id, "job_id": job.job_id},
            workflow_id=f"expense-ocr-{job.job_id}",
            id_prefix="expense-ocr",
            task_queue=self.task_queue,
        )
