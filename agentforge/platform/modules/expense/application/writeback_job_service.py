"""写回任务服务模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agentforge.platform.modules.expense.application.ledger_service import ExpenseLedgerService
from agentforge.platform.modules.expense.domain.ledger import ExpenseWritebackItem
from agentforge.platform.modules.expense.domain.writeback_job import (
    ExpenseWritebackJob,
    ExpenseWritebackJobStatus,
)
from agentforge.platform.modules.expense.ports import ExpenseWritebackJobRepository
from agentforge.platform.sdk.ports import WorkflowClientPort

MAX_WRITEBACK_JOB_CLAIMS = 5000
WRITEBACK_CHUNK_SIZE = 200


class ExpenseWritebackJobService:
    """报销写回任务应用服务，编排领域用例及其副作用。"""

    task_queue = "expense-copilot"

    def __init__(
        self,
        repository: ExpenseWritebackJobRepository,
        ledger: ExpenseLedgerService,
        workflow_client: WorkflowClientPort | None = None,
    ) -> None:
        """初始化 ExpenseWritebackJobService。

        Args:
            repository: 数据仓储实现。
            ledger: 台账。
            workflow_client: 工作流客户端。
        """
        self._repository = repository
        self._ledger = ledger
        self._workflow_client = workflow_client

    async def enqueue(
        self,
        tenant_id: str,
        *,
        connector_id: str,
        action: str,
        actor_id: str,
        claim_ids: list[str] | None = None,
    ) -> ExpenseWritebackJob:
        """写入队列报销写回任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。
            claim_ids: 报销单 ID 列表。

        Returns:
            报销写回任务结果。
        """
        connector_id, action, actor_id = await self._ledger.authorize_writeback(
            tenant_id,
            connector_id=connector_id,
            action=action,
            actor_id=actor_id,
        )
        resolved = await self._ledger.resolve_claim_ids(
            tenant_id,
            claim_ids,
            max_claims=MAX_WRITEBACK_JOB_CLAIMS,
        )
        job = ExpenseWritebackJob(
            job_id=str(uuid4()),
            tenant_id=tenant_id,
            connector_id=connector_id,
            action=action,
            actor_id=actor_id,
            claim_ids=resolved,
            total_claims=len(resolved),
        )
        await self._repository.save(job)
        await self._dispatch(job)
        return await self.get(tenant_id, job.job_id)

    async def get(self, tenant_id: str, job_id: str) -> ExpenseWritebackJob:
        """读取报销写回任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销写回任务结果。

        Raises:
            LookupError: 操作无法完成时抛出。
        """
        job = await self._repository.get(tenant_id, job_id)
        if job is None:
            raise LookupError("writeback job not found")
        return job

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseWritebackJob]:
        """查询报销写回任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        return await self._repository.list(tenant_id, limit=limit)

    async def summary(self, tenant_id: str) -> dict[str, object]:
        """汇总报销写回任务信息。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        jobs = await self._repository.list(tenant_id, limit=10_000)
        counts = {status.value: 0 for status in ExpenseWritebackJobStatus}
        for job in jobs:
            counts[job.status.value] += 1
        succeeded = counts[ExpenseWritebackJobStatus.SUCCEEDED.value]
        return {
            "tenant_id": tenant_id,
            "total": len(jobs),
            "by_status": counts,
            "success_rate": round(succeeded / len(jobs), 4) if jobs else 0.0,
            "total_claims": sum(job.total_claims for job in jobs),
            "total_attempts": sum(job.attempts for job in jobs),
        }

    async def process(self, tenant_id: str, job_id: str) -> ExpenseWritebackJob:
        """处理报销写回任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销写回任务结果。
        """
        job = await self.get(tenant_id, job_id)
        if job.status == ExpenseWritebackJobStatus.SUCCEEDED:
            return job
        job.status = ExpenseWritebackJobStatus.RUNNING
        job.attempts += 1
        job.error = ""
        job.updated_at = datetime.now(timezone.utc)
        await self._repository.save(job)
        items: list[ExpenseWritebackItem] = []
        try:
            for offset in range(0, len(job.claim_ids), WRITEBACK_CHUNK_SIZE):
                batch = await self._ledger.writeback(
                    job.tenant_id,
                    connector_id=job.connector_id,
                    action=job.action,
                    actor_id=job.actor_id,
                    claim_ids=job.claim_ids[offset : offset + WRITEBACK_CHUNK_SIZE],
                )
                items.extend(batch.items)
                _apply_progress(job, items)
                await self._repository.save(job)
            _apply_results(job, items)
        except Exception as exc:  # noqa: BLE001 - persisted for operator retry
            job.status = ExpenseWritebackJobStatus.FAILED
            job.error = str(exc)[:1000]
        job.updated_at = datetime.now(timezone.utc)
        await self._repository.save(job)
        return job

    async def retry_failed(self, tenant_id: str, job_id: str) -> ExpenseWritebackJob:
        """重试失败。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销写回任务结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        job = await self.get(tenant_id, job_id)
        if job.status not in {
            ExpenseWritebackJobStatus.FAILED,
            ExpenseWritebackJobStatus.PARTIAL_FAILED,
        }:
            raise ValueError("only failed or partially failed writeback jobs can be retried")
        job.status = ExpenseWritebackJobStatus.QUEUED
        job.error = ""
        job.updated_at = datetime.now(timezone.utc)
        await self._repository.save(job)
        await self._dispatch(job)
        return await self.get(tenant_id, job.job_id)

    async def _dispatch(self, job: ExpenseWritebackJob) -> None:
        """分发报销写回任务。

        Args:
            job: 后台任务对象。
        """
        if self._workflow_client is None:
            await self.process(job.tenant_id, job.job_id)
            return
        from agentforge.platform.modules.expense.workflows.ledger_writeback import (
            ExpenseLedgerWritebackWorkflow,
        )

        await self._workflow_client.start_workflow(
            ExpenseLedgerWritebackWorkflow.run,
            {"tenant_id": job.tenant_id, "job_id": job.job_id},
            workflow_id=f"expense-ledger-writeback-{job.job_id}",
            id_prefix="expense-ledger-writeback",
            task_queue=self.task_queue,
        )


def _apply_results(job: ExpenseWritebackJob, items: list[ExpenseWritebackItem]) -> None:
    """应用结果。

    Args:
        job: 后台任务对象。
        items: 待处理条目列表。
    """
    job.items = items
    job.total_claims = len(items)
    job.succeeded_claims = sum(item.status.value == "succeeded" for item in items)
    job.failed_claims = sum(item.status.value == "failed" for item in items)
    job.skipped_claims = sum(item.status.value == "skipped" for item in items)
    if job.failed_claims == 0:
        job.status = ExpenseWritebackJobStatus.SUCCEEDED
    elif job.succeeded_claims or job.skipped_claims:
        job.status = ExpenseWritebackJobStatus.PARTIAL_FAILED
    else:
        job.status = ExpenseWritebackJobStatus.FAILED


def _apply_progress(job: ExpenseWritebackJob, items: list[ExpenseWritebackItem]) -> None:
    """应用进度。

    Args:
        job: 后台任务对象。
        items: 待处理条目列表。
    """
    job.items = list(items)
    job.succeeded_claims = sum(item.status.value == "succeeded" for item in items)
    job.failed_claims = sum(item.status.value == "failed" for item in items)
    job.skipped_claims = sum(item.status.value == "skipped" for item in items)
    job.updated_at = datetime.now(timezone.utc)
