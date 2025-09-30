from __future__ import annotations

from datetime import datetime, timezone

from agentforge.platform.domain.reporting import ScheduledReport


class MemoryScheduledReportRepository:
    """In-memory scheduled report repository."""

    def __init__(self) -> None:
        self._reports: dict[str, ScheduledReport] = {}

    async def save(self, report: ScheduledReport) -> None:
        self._reports[report.report_id] = report

    async def get(self, report_id: str) -> ScheduledReport | None:
        return self._reports.get(report_id)

    async def list_schedules(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ScheduledReport]:
        items = [r for r in self._reports.values() if tenant_id is None or r.tenant_id == tenant_id]
        return items[:limit]

    async def delete(self, report_id: str) -> None:
        self._reports.pop(report_id, None)

    async def list_due(
        self,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[ScheduledReport]:
        now = before or datetime.now(timezone.utc)
        return [r for r in self._reports.values() if r.enabled and r.next_run_at <= now][:limit]
