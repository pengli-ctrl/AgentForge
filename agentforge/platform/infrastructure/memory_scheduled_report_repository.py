"""记忆报告仓储模块。"""

from __future__ import annotations

from datetime import datetime, timezone

from agentforge.platform.domain.reporting import ScheduledReport


class MemoryScheduledReportRepository:
    """报告仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryScheduledReportRepository。"""
        self._reports: dict[str, ScheduledReport] = {}

    async def save(self, report: ScheduledReport) -> None:
        """保存报告。

        Args:
            report: 报告。
        """
        self._reports[report.report_id] = report

    async def get(self, report_id: str) -> ScheduledReport | None:
        """获取报告。

        Args:
            report_id: 报告 ID。

        Returns:
            报告无结果。
        """
        return self._reports.get(report_id)

    async def list_schedules(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ScheduledReport]:
        """查询调度。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        items = [r for r in self._reports.values() if tenant_id is None or r.tenant_id == tenant_id]
        return items[:limit]

    async def delete(self, report_id: str) -> None:
        """删除报告。

        Args:
            report_id: 报告 ID。
        """
        self._reports.pop(report_id, None)

    async def list_due(
        self,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[ScheduledReport]:
        """查询到期。

        Args:
            before: 之前。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        now = before or datetime.now(timezone.utc)
        return [r for r in self._reports.values() if r.enabled and r.next_run_at <= now][:limit]
