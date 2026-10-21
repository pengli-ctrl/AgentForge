"""记忆OCR任务仓储模块。"""

from __future__ import annotations

from copy import deepcopy

from agentforge.platform.modules.expense.domain.ocr_job import ExpenseOcrJob


class MemoryExpenseOcrJobRepository:
    """报销OCR任务仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryExpenseOcrJobRepository。"""
        self._jobs: dict[str, ExpenseOcrJob] = {}

    async def save(self, job: ExpenseOcrJob) -> None:
        """保存报销OCR任务。

        Args:
            job: 后台任务对象。
        """
        self._jobs[job.job_id] = deepcopy(job)

    async def get(self, tenant_id: str, job_id: str) -> ExpenseOcrJob | None:
        """读取报销OCR任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销OCR任务无结果。
        """
        job = self._jobs.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            return None
        return deepcopy(job)

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseOcrJob]:
        """查询报销OCR任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        jobs = [job for job in self._jobs.values() if job.tenant_id == tenant_id]
        jobs.sort(key=lambda job: (job.created_at, job.job_id), reverse=True)
        return [deepcopy(job) for job in jobs[:limit]]
