from __future__ import annotations

import builtins
from datetime import datetime

from agentforge.platform.domain.reporting import ReportRun, _decode_run_cursor, _encode_run_cursor


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
        archived: bool | None = None,
    ) -> list[ReportRun]:
        items = [
            r
            for r in self._runs.values()
            if (tenant_id is None or r.tenant_id == tenant_id)
            and (report_type is None or r.report_type.value == report_type)
            and (archived is None or r.archived == archived)
        ]
        items.sort(key=lambda r: r.generated_at, reverse=True)
        return items[:limit]

    async def list_page(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
        cursor: str | None = None,
    ) -> tuple[builtins.list[ReportRun], str | None]:
        items = [
            r
            for r in self._runs.values()
            if (tenant_id is None or r.tenant_id == tenant_id)
            and (report_type is None or r.report_type.value == report_type)
            and (archived is None or r.archived == archived)
        ]
        items.sort(key=lambda r: (r.generated_at, r.run_id), reverse=True)
        anchor = _decode_run_cursor(cursor)
        if anchor is not None:
            anchor_ts, anchor_id = anchor
            items = [r for r in items if (r.generated_at, r.run_id) < (anchor_ts, anchor_id)]
        probe = items[: limit + 1]
        page = probe[:limit]
        next_cursor = (
            _encode_run_cursor(page[-1].generated_at, page[-1].run_id)
            if len(probe) > limit
            else None
        )
        return page, next_cursor

    async def set_archived(self, run_id: str, archived: bool) -> None:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        run.archived = archived

    async def delete_older_than(
        self,
        cutoff: datetime,
        tenant_id: str | None = None,
        include_archived: bool = False,
    ) -> int:
        removed = [
            r.run_id
            for r in self._runs.values()
            if r.generated_at < cutoff
            and (tenant_id is None or r.tenant_id == tenant_id)
            and (include_archived or not r.archived)
        ]
        for run_id in removed:
            self._runs.pop(run_id, None)
        return len(removed)
