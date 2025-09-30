from __future__ import annotations

from agentforge.platform.domain.reporting import ReportRun


class MemoryReportRunRepository:
    """In-memory persisted report run repository."""

    def __init__(self) -> None:
        self._runs: dict[str, ReportRun] = {}

    async def save(self, run: ReportRun) -> None:
        self._runs[run.run_id] = run

    async def get(self, run_id: str) -> ReportRun | None:
        return self._runs.get(run_id)

    async def list(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
    ) -> list[ReportRun]:
        items = [
            r
            for r in self._runs.values()
            if (tenant_id is None or r.tenant_id == tenant_id)
            and (report_type is None or r.report_type.value == report_type)
        ]
        items.sort(key=lambda r: r.generated_at, reverse=True)
        return items[:limit]
