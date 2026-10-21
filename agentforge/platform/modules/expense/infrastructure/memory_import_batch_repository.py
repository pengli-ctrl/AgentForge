"""记忆导入批次仓储模块。"""

from __future__ import annotations

from copy import deepcopy

from agentforge.platform.modules.expense.domain.import_batch import ExpenseImportBatch


class MemoryExpenseImportBatchRepository:
    """报销导入批次仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryExpenseImportBatchRepository。"""
        self._batches: dict[str, ExpenseImportBatch] = {}

    async def save(self, batch: ExpenseImportBatch) -> None:
        """保存报销导入批次。

        Args:
            batch: 批次。
        """
        self._batches[batch.batch_id] = deepcopy(batch)

    async def get(self, tenant_id: str, batch_id: str) -> ExpenseImportBatch | None:
        """获取报销导入批次。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            batch_id: 批次 ID。

        Returns:
            报销导入批次无结果。
        """
        batch = self._batches.get(batch_id)
        if batch is None or batch.tenant_id != tenant_id:
            return None
        return deepcopy(batch)

    async def list(self, tenant_id: str, limit: int = 100) -> list[ExpenseImportBatch]:
        """查询报销导入批次。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        batches = [batch for batch in self._batches.values() if batch.tenant_id == tenant_id]
        batches.sort(key=lambda batch: (batch.created_at, batch.batch_id), reverse=True)
        return [deepcopy(batch) for batch in batches[:limit]]
