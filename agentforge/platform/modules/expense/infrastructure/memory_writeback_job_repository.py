"""记忆写回任务仓储模块。"""

from __future__ import annotations

from copy import deepcopy

from agentforge.platform.modules.expense.domain.writeback_job import ExpenseWritebackJob


class MemoryExpenseWritebackJobRepository:
    """报销写回任务仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryExpenseWritebackJobRepository。"""
        self._jobs: dict[str, ExpenseWritebackJob] = {}

    async def save(self, job: ExpenseWritebackJob) -> None:
        """保存报销写回任务。

        Args:
            job: 后台任务对象。
        """
        self._jobs[job.job_id] = deepcopy(job)

    async def get(self, tenant_id: str, job_id: str) -> ExpenseWritebackJob | None:
        """读取报销写回任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            job_id: 任务 ID。

        Returns:
            报销写回任务无结果。
        """
        job = self._jobs.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            return None
        return deepcopy(job)

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseWritebackJob]:
        """查询报销写回任务。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        jobs = [job for job in self._jobs.values() if job.tenant_id == tenant_id]
        jobs.sort(key=lambda job: (job.created_at, job.job_id), reverse=True)
        return [deepcopy(job) for job in jobs[:limit]]
