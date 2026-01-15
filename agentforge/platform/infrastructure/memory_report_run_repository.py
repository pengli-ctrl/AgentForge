"""AgentForge 平台基础设施层：memory_report_run_repository。

本模块提供 memory_report_run_repository 的内存实现，用于单元测试、本地开发和离线验证。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryReportRunRepository。
"""

from __future__ import annotations

import builtins
from datetime import datetime

from agentforge.platform.domain.reporting import ReportRun, _decode_run_cursor, _encode_run_cursor


class MemoryReportRunRepository:
    """MemoryReportRunRepository。

    MemoryReportRunRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save()。
    - 方法 get()。
    - 方法 list()。
    - 方法 list_page()。
    - 方法 set_archived()。
    - 方法 delete_older_than()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._runs: dict[str, ReportRun] = {}

    async def save(self, run: ReportRun) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            run: ReportRun，调用方传入的 run 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._runs[run.run_id] = run

    async def get(self, run_id: str) -> ReportRun | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            run_id: str，调用方传入的 run_id 参数。

        Returns:
            ReportRun | None，函数执行后的结果。
        """
        return self._runs.get(run_id)

    async def list(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
    ) -> list[ReportRun]:
        """执行 list 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            report_type: str | None，调用方传入的 report_type 参数。
            limit: int，调用方传入的 limit 参数。
            archived: bool | None，调用方传入的 archived 参数。

        Returns:
            list[ReportRun]，函数执行后的结果。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            report_type: str | None，调用方传入的 report_type 参数。
            limit: int，调用方传入的 limit 参数。
            archived: bool | None，调用方传入的 archived 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            tuple[builtins.list[ReportRun], str | None]，函数执行后的结果。
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
        """执行 set_archived 对应的逻辑，并返回处理结果。

        Args:
            run_id: str，调用方传入的 run_id 参数。
            archived: bool，调用方传入的 archived 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            KeyError: 当输入、状态或外部依赖不满足要求时抛出。
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
        """删除指定数据，并返回调用方需要的结果。

        Args:
            cutoff: datetime，调用方传入的 cutoff 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            include_archived: bool，调用方传入的 include_archived 参数。

        Returns:
            int，函数执行后的结果。
        """
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
