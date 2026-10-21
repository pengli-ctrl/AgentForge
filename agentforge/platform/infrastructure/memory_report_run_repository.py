"""记忆报告运行仓储模块。"""

from __future__ import annotations

import builtins
from datetime import datetime

from agentforge.platform.domain.reporting import ReportRun, _decode_run_cursor, _encode_run_cursor


class MemoryReportRunRepository:
    """报告运行仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryReportRunRepository。"""
        self._runs: dict[str, ReportRun] = {}

    async def save(self, run: ReportRun) -> None:
        """保存报告运行。

        Args:
            run: 运行。
        """
        self._runs[run.run_id] = run

    async def get(self, run_id: str) -> ReportRun | None:
        """获取报告运行。

        Args:
            run_id: 运行记录 ID。

        Returns:
            报告运行无结果。
        """
        return self._runs.get(run_id)

    async def list(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
    ) -> list[ReportRun]:
        """查询报告运行。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            report_type: 报告类型。
            limit: 返回记录的最大数量。
            archived: 已归档。

        Returns:
            结果列表。
        """
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
        """查询页面。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            report_type: 报告类型。
            limit: 返回记录的最大数量。
            archived: 已归档。
            cursor: 分页游标。

        Returns:
            结果元组。
        """
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
        """设置已归档。

        Args:
            run_id: 运行记录 ID。
            archived: 已归档。

        Raises:
            KeyError: 缺少必要配置或目标对象时抛出。
        """
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
        """删除更旧比。

        Args:
            cutoff: 截止时间。
            tenant_id: 租户 ID，用于数据隔离。
            include_archived: 已归档。

        Returns:
            整数结果。
        """
        removed = [
            r.run_id
            for r in self._runs.values()
            if r.generated_at <= cutoff
            and (tenant_id is None or r.tenant_id == tenant_id)
            and (include_archived or not r.archived)
        ]
        for run_id in removed:
            self._runs.pop(run_id, None)
        return len(removed)
