"""AgentForge 平台基础设施层：memory_scheduled_report_repository。

本模块提供 memory_scheduled_report_repository 的内存实现，用于单元测试、本地开发和离线验证。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryScheduledReportRepository。
"""

from __future__ import annotations

from datetime import datetime, timezone

from agentforge.platform.domain.reporting import ScheduledReport


class MemoryScheduledReportRepository:
    """MemoryScheduledReportRepository。

    MemoryScheduledReportRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save()。
    - 方法 get()。
    - 方法 list_schedules()。
    - 方法 delete()。
    - 方法 list_due()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._reports: dict[str, ScheduledReport] = {}

    async def save(self, report: ScheduledReport) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            report: ScheduledReport，调用方传入的 report 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._reports[report.report_id] = report

    async def get(self, report_id: str) -> ScheduledReport | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            report_id: str，调用方传入的 report_id 参数。

        Returns:
            ScheduledReport | None，函数执行后的结果。
        """
        return self._reports.get(report_id)

    async def list_schedules(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ScheduledReport]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[ScheduledReport]，函数执行后的结果。
        """
        items = [r for r in self._reports.values() if tenant_id is None or r.tenant_id == tenant_id]
        return items[:limit]

    async def delete(self, report_id: str) -> None:
        """执行 delete 对应的核心操作，并保持调用契约稳定。

        Args:
            report_id: str，调用方传入的 report_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._reports.pop(report_id, None)

    async def list_due(
        self,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[ScheduledReport]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            before: datetime | None，调用方传入的 before 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[ScheduledReport]，函数执行后的结果。
        """
        now = before or datetime.now(timezone.utc)
        return [r for r in self._reports.values() if r.enabled and r.next_run_at <= now][:limit]
