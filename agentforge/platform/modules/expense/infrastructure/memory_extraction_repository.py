"""记忆提取仓储模块。"""

from __future__ import annotations

from copy import deepcopy

from agentforge.platform.modules.expense.domain.extraction import ExpenseExtractionRecord


class MemoryExpenseExtractionRepository:
    """报销提取仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryExpenseExtractionRepository。"""
        self._records: dict[str, ExpenseExtractionRecord] = {}

    async def save(self, record: ExpenseExtractionRecord) -> None:
        """保存报销提取。

        Args:
            record: 待处理的领域记录。
        """
        self._records[record.extraction_id] = deepcopy(record)

    async def get(self, tenant_id: str, extraction_id: str) -> ExpenseExtractionRecord | None:
        """读取报销提取。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            extraction_id: 提取 ID。

        Returns:
            报销提取记录无结果。
        """
        record = self._records.get(extraction_id)
        if record is None or record.tenant_id != tenant_id:
            return None
        return deepcopy(record)
