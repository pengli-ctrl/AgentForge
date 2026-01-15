"""AgentForge 平台应用服务层：report_service。

本模块实现 report_service 应用服务，编排多个领域对象和基础设施组件完成业务流程。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ReportService。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.cron import CronSchedule, is_cron_cadence
from agentforge.platform.domain.reporting import (
    OperationsReport,
    ReportFormat,
    ReportRun,
    ReportType,
    ScheduledReport,
)
from agentforge.platform.domain.ticket import RiskLevel


def _now() -> datetime:
    """执行 _now 对应的逻辑，并返回处理结果。

    Returns:
        datetime，函数执行后的结果。
    """
    return datetime.now(timezone.utc)


def _advance_next_run(cadence: str, last_run: datetime) -> datetime:
    """执行 _advance_next_run 对应的逻辑，并返回处理结果。

    Args:
        cadence: str，调用方传入的 cadence 参数。
        last_run: datetime，调用方传入的 last_run 参数。

    Returns:
        datetime，函数执行后的结果。
    """
    if is_cron_cadence(cadence):
        return CronSchedule(cadence).next_run_from(last_run=last_run, now=_now())
    if cadence == "weekly":
        return last_run + timedelta(days=7)
    if cadence == "monthly":
        return last_run + timedelta(days=30)
    return last_run + timedelta(days=1)  # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。


class ReportService:
    """ReportService。

    ReportService 编排业务流程，协调仓储、模型、策略和外部连接器完成用例。

    主要成员：
    - 方法 generate()。
    - 方法 list_runs()。
    - 方法 list_runs_paginated()。
    - 方法 get_run()。
    - 方法 archive_run()。
    - 方法 export_archive()。
    - 方法 export_archive_to()。
    - 方法 prune_runs()。
    - 方法 schedule()。
    - 方法 list_schedules()。
    - 方法 delete_schedule()。
    - 方法 set_schedule_enabled()。
    - 方法 run_due()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        cost_repository,
        audit_repository,
        regression_repository,
        schedule_repository,
        run_repository,
        default_retention_days: int | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            cost_repository: Any，调用方传入的 cost_repository 参数。
            audit_repository: Any，调用方传入的 audit_repository 参数。
            regression_repository: Any，调用方传入的 regression_repository 参数。
            schedule_repository: Any，调用方传入的 schedule_repository 参数。
            run_repository: Any，调用方传入的 run_repository 参数。
            default_retention_days: int | None，调用方传入的 default_retention_days 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._cost = cost_repository
        self._audit = audit_repository
        self._regression = regression_repository
        self._schedules = schedule_repository
        self._runs = run_repository
        # 验证数据保留策略，确保不会无限累积。
        # 验证数据保留策略，确保不会无限累积。
        # 调度任务管理。
        self._default_retention_days = default_retention_days

    async def _persist(self, report: OperationsReport) -> ReportRun:
        """执行 _persist 对应的逻辑，并返回处理结果。

        Args:
            report: OperationsReport，调用方传入的 report 参数。

        Returns:
            ReportRun，函数执行后的结果。
        """
        run = ReportRun.from_operations(report)
        await self._runs.save(run)
        return run

    async def _record_audit(
        self,
        tenant_id: str | None,
        action: str,
        resource_type: str = "report",
        resource_id: str = "",
        risk_level: RiskLevel = RiskLevel.LOW,
        payload: dict | None = None,
    ) -> None:
        """执行 _record_audit 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            action: str，调用方传入的 action 参数。
            resource_type: str，调用方传入的 resource_type 参数。
            resource_id: str，调用方传入的 resource_id 参数。
            risk_level: RiskLevel，调用方传入的 risk_level 参数。
            payload: dict | None，调用方传入的 payload 参数。

        Returns:
            None，函数执行后的结果。
        """
        if self._audit is None:
            return
        await self._audit.save(
            AuditEvent(
                event_id=uuid.uuid4().hex,
                tenant_id=tenant_id or "system",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                risk_level=risk_level,
                actor_type="admin",
                actor_id="console",
                payload=payload or {},
            )
        )

    async def generate(
        self,
        report_type: ReportType,
        tenant_id: str,
        fmt: ReportFormat = ReportFormat.JSON,
        days: int = 30,
        report_id: str | None = None,
        scheduled_report_id: str | None = None,
    ) -> OperationsReport:
        """执行 generate 对应的逻辑，并返回处理结果。

        Args:
            report_type: ReportType，调用方传入的 report_type 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。
            fmt: ReportFormat，调用方传入的 fmt 参数。
            days: int，调用方传入的 days 参数。
            report_id: str | None，调用方传入的 report_id 参数。
            scheduled_report_id: str | None，调用方传入的 scheduled_report_id 参数。

        Returns:
            OperationsReport，函数执行后的结果。
        """
        report_id = report_id or uuid.uuid4().hex[:16]
        if report_type == ReportType.COST:
            rows, summary = await self._build_cost(tenant_id, days)
        elif report_type == ReportType.AUDIT:
            rows, summary = await self._build_audit(tenant_id)
        else:  # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
            rows, summary = await self._build_quality(tenant_id)

        report = OperationsReport(
            report_id=report_id,
            tenant_id=tenant_id,
            report_type=report_type,
            format=fmt,
            rows=rows,
            summary=summary,
            generated_at=_now(),
            scheduled_report_id=scheduled_report_id,
        )
        await self._persist(report)
        await self._record_audit(
            tenant_id=tenant_id,
            action="report.generate",
            resource_id=report.report_id,
            payload={
                "report_type": report.report_type.value,
                "format": report.format.value,
                "rows": len(report.rows),
                "scheduled_report_id": report.scheduled_report_id,
            },
        )
        return report

    async def list_runs(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
    ) -> list[dict]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            report_type: str | None，调用方传入的 report_type 参数。
            limit: int，调用方传入的 limit 参数。
            archived: bool | None，调用方传入的 archived 参数。

        Returns:
            list[dict]，函数执行后的结果。
        """
        items = await self._runs.list(
            tenant_id=tenant_id,
            report_type=report_type.value if isinstance(report_type, ReportType) else report_type,
            limit=limit,
            archived=archived,
        )
        return [self._run_meta(i) for i in items]

    async def list_runs_paginated(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
        cursor: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            report_type: str | None，调用方传入的 report_type 参数。
            limit: int，调用方传入的 limit 参数。
            archived: bool | None，调用方传入的 archived 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            tuple[list[dict], str | None]，函数执行后的结果。
        """
        items, next_cursor = await self._runs.list_page(
            tenant_id=tenant_id,
            report_type=report_type.value if isinstance(report_type, ReportType) else report_type,
            limit=limit,
            archived=archived,
            cursor=cursor,
        )
        return [self._run_meta(i) for i in items], next_cursor

    async def get_run(self, run_id: str) -> ReportRun | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            run_id: str，调用方传入的 run_id 参数。

        Returns:
            ReportRun | None，函数执行后的结果。
        """
        return await self._runs.get(run_id)

    async def archive_run(self, run_id: str, archived: bool) -> dict:
        """执行 archive_run 对应的逻辑，并返回处理结果。

        Args:
            run_id: str，调用方传入的 run_id 参数。
            archived: bool，调用方传入的 archived 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            KeyError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        run = await self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        await self._runs.set_archived(run_id, archived=archived)
        run.archived = archived
        await self._record_audit(
            tenant_id=run.tenant_id,
            action="report.run.archive" if archived else "report.run.unarchive",
            resource_id=run_id,
            payload={"archived": archived},
        )
        return {"run_id": run_id, "archived": archived}

    async def export_archive(
        self, tenant_id: str | None = None, limit: int = 100
    ) -> tuple[bytes, str]:
        """执行 export_archive 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            tuple[bytes, str]，函数执行后的结果。
        """
        import io

        buf = io.BytesIO()
        info = await self._write_archive(buf, tenant_id=tenant_id, limit=limit)
        return buf.getvalue(), info

    async def export_archive_to(
        self,
        sink,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> str:
        """执行 export_archive_to 对应的逻辑，并返回处理结果。

        Args:
            sink: Any，调用方传入的 sink 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            str，函数执行后的结果。
        """
        return await self._write_archive(sink, tenant_id=tenant_id, limit=limit)

    async def _write_archive(self, sink, tenant_id: str | None = None, limit: int = 100) -> str:
        """执行 _write_archive 对应的逻辑，并返回处理结果。

        Args:
            sink: Any，调用方传入的 sink 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            str，函数执行后的结果。
        """
        import zipfile

        runs = await self._runs.list(tenant_id=tenant_id, limit=limit)
        outputs: list[dict] = []
        with zipfile.ZipFile(sink, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for run in runs:
                ext = "json" if run.format == ReportFormat.JSON else "csv"
                content = run.to_json() if run.format == ReportFormat.JSON else run.to_csv()
                name = f"run_{run.run_id}.{ext}"
                zf.writestr(name, content)
                outputs.append(
                    {
                        "run_id": run.run_id,
                        "tenant_id": run.tenant_id,
                        "report_type": run.report_type.value,
                        "format": run.format.value,
                        "file": name,
                        "generated_at": run.generated_at.isoformat(),
                        "archived": run.archived,
                    }
                )
        await self._record_audit(
            tenant_id=tenant_id,
            action="report.archive.export",
            payload={"count": len(outputs), "tenant_id": tenant_id, "limit": limit},
        )
        return json.dumps({"count": len(outputs), "files": outputs})

    async def prune_runs(
        self,
        retention_days: int,
        tenant_id: str | None = None,
        include_archived: bool = False,
    ) -> dict:
        """执行 prune_runs 对应的逻辑，并返回处理结果。

        Args:
            retention_days: int，调用方传入的 retention_days 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            include_archived: bool，调用方传入的 include_archived 参数。

        Returns:
            dict，函数执行后的结果。
        """
        cutoff = _now() - timedelta(days=retention_days)
        removed = await self._runs.delete_older_than(
            cutoff=cutoff, tenant_id=tenant_id, include_archived=include_archived
        )
        await self._record_audit(
            tenant_id=tenant_id,
            action="report.runs.prune",
            risk_level=RiskLevel.MEDIUM,
            payload={
                "retention_days": retention_days,
                "cutoff": cutoff.isoformat(),
                "include_archived": include_archived,
                "removed": removed,
            },
        )
        return {
            "retention_days": retention_days,
            "cutoff": cutoff.isoformat(),
            "tenant_id": tenant_id,
            "include_archived": include_archived,
            "removed": removed,
        }

    @staticmethod
    def _run_meta(run: ReportRun) -> dict:
        """执行 _run_meta 对应的逻辑，并返回处理结果。

        Args:
            run: ReportRun，调用方传入的 run 参数。

        Returns:
            dict，函数执行后的结果。
        """
        return {
            "run_id": run.run_id,
            "tenant_id": run.tenant_id,
            "report_type": run.report_type.value,
            "format": run.format.value,
            "rows": len(run.rows),
            "summary": run.summary,
            "generated_at": run.generated_at.isoformat(),
            "scheduled_report_id": run.scheduled_report_id,
            "archived": run.archived,
        }

    async def _build_cost(self, tenant_id: str, days: int) -> tuple[list[dict], dict]:
        """执行 _build_cost 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            days: int，调用方传入的 days 参数。

        Returns:
            tuple[list[dict], dict]，函数执行后的结果。
        """
        daily = await self._cost.daily_summary(tenant_id, days=days)
        rows = [
            {
                "date": d["date"],
                "request_count": d["request_count"],
                "amount": round(d["amount"], 4),
            }
            for d in daily
        ]
        summary = {
            "tenant_id": tenant_id,
            "days": days,
            "total_amount": round(sum(r["amount"] for r in rows), 4),
            "total_requests": sum(r["request_count"] for r in rows),
            "rows": len(rows),
        }
        return rows, summary

    async def _build_audit(self, tenant_id: str) -> tuple[list[dict], dict]:
        """执行 _build_audit 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            tuple[list[dict], dict]，函数执行后的结果。
        """
        events, _ = await self._audit.query_events(tenant_id=tenant_id, limit=500)
        rows = [
            {
                "event_id": e.event_id,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "risk_level": e.risk_level.value,
                "actor_id": e.actor_id,
                "created_at": e.occurred_at.isoformat() if e.occurred_at else "",
            }
            for e in events
        ]
        summary = {"tenant_id": tenant_id, "event_count": len(rows)}
        return rows, summary

    async def _build_quality(self, tenant_id: str) -> tuple[list[dict], dict]:
        """执行 _build_quality 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            tuple[list[dict], dict]，函数执行后的结果。
        """
        runs = await self._regression.list_runs(tenant_id, limit=100)
        rows = [
            {
                "run_id": r.run_id,
                "candidate_id": r.candidate_id,
                "status": r.status.value,
                "verdict": r.verdict,
                "recall_at_k": r.recall_at_k,
                "citation_accuracy": r.citation_accuracy,
                "classification_accuracy": r.classification_accuracy,
                "priority_accuracy": r.priority_accuracy,
                "structured_output_rate": r.structured_output_rate,
                "high_risk_miss_rate": r.high_risk_miss_rate,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in runs
        ]
        avg = {}
        if rows:
            avg = {
                "recall_at_k": round(sum(r["recall_at_k"] for r in rows) / len(rows), 4),
                "citation_accuracy": round(
                    sum(r["citation_accuracy"] for r in rows) / len(rows), 4
                ),
                "classification_accuracy": round(
                    sum(r["classification_accuracy"] for r in rows) / len(rows), 4
                ),
                "high_risk_miss_rate": round(
                    sum(r["high_risk_miss_rate"] for r in rows) / len(rows), 4
                ),
            }
        summary = {"tenant_id": tenant_id, "run_count": len(rows), "averages": avg}
        return rows, summary

    # 调度任务管理。

    async def schedule(
        self,
        tenant_id: str,
        report_type: ReportType,
        cadence: str = "daily",
        report_id: str | None = None,
        retention_days: int | None = None,
    ) -> ScheduledReport:
        """执行 schedule 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            report_type: ReportType，调用方传入的 report_type 参数。
            cadence: str，调用方传入的 cadence 参数。
            report_id: str | None，调用方传入的 report_id 参数。
            retention_days: int | None，调用方传入的 retention_days 参数。

        Returns:
            ScheduledReport，函数执行后的结果。
        """
        report_id = report_id or uuid.uuid4().hex[:16]
        now = _now()
        sched = ScheduledReport(
            report_id=report_id,
            tenant_id=tenant_id,
            report_type=report_type,
            cadence=cadence,
            enabled=True,
            retention_days=retention_days,
            created_at=now,
            last_run_at=None,
            next_run_at=now,
        )
        await self._schedules.save(sched)
        await self._record_audit(
            tenant_id=tenant_id,
            action="report.schedule.create",
            resource_id=report_id,
            payload={
                "report_type": report_type.value,
                "cadence": cadence,
                "retention_days": retention_days,
            },
        )
        return sched

    async def list_schedules(self, tenant_id: str | None = None, limit: int = 100) -> list[dict]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[dict]，函数执行后的结果。
        """
        items = await self._schedules.list_schedules(tenant_id=tenant_id, limit=limit)
        return [i.model_dump(mode="json") for i in items]

    async def delete_schedule(self, report_id: str) -> None:
        """删除指定数据，并返回调用方需要的结果。

        Args:
            report_id: str，调用方传入的 report_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        sched = await self._schedules.get(report_id)
        await self._schedules.delete(report_id)
        await self._record_audit(
            tenant_id=sched.tenant_id if sched is not None else None,
            action="report.schedule.delete",
            resource_id=report_id,
        )

    async def set_schedule_enabled(self, report_id: str, enabled: bool) -> ScheduledReport:
        """执行 set_schedule_enabled 对应的逻辑，并返回处理结果。

        Args:
            report_id: str，调用方传入的 report_id 参数。
            enabled: bool，调用方传入的 enabled 参数。

        Returns:
            ScheduledReport，函数执行后的结果。

        Raises:
            KeyError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        sched = await self._schedules.get(report_id)
        if sched is None:
            raise KeyError(report_id)
        sched.enabled = enabled
        await self._schedules.save(sched)
        await self._record_audit(
            tenant_id=sched.tenant_id,
            action="report.schedule.enable" if enabled else "report.schedule.disable",
            resource_id=report_id,
            payload={"enabled": enabled},
        )
        return sched

    async def run_due(
        self,
        fmt: ReportFormat = ReportFormat.JSON,
        default_retention_days: int | None = None,
    ) -> dict:
        """执行完整流程，并返回调用方需要的结果。

        Args:
            fmt: ReportFormat，调用方传入的 fmt 参数。
            default_retention_days: int | None，调用方传入的 default_retention_days 参数。

        Returns:
            dict，函数执行后的结果。
        """
        effective_default = (
            default_retention_days
            if default_retention_days is not None
            else self._default_retention_days
        )
        now = _now()
        due = await self._schedules.list_due(before=now)
        reports = []
        pruned = 0
        retention_tenants: dict[str, int] = {}
        for sched in due:
            retention = sched.retention_days
            if retention is None:
                retention = effective_default
            if retention:
                # 验证数据保留策略，确保不会无限累积。
                current = retention_tenants.get(sched.tenant_id)
                if current is None or retention < current:
                    retention_tenants[sched.tenant_id] = retention
            report = await self.generate(
                report_type=sched.report_type,
                tenant_id=sched.tenant_id,
                fmt=fmt,
                scheduled_report_id=sched.report_id,
            )
            sched.last_run_at = now
            sched.next_run_at = _advance_next_run(sched.cadence, now)
            await self._schedules.save(sched)
            reports.append(
                {
                    "report_id": report.report_id,
                    "scheduled_report_id": sched.report_id,
                    "tenant_id": sched.tenant_id,
                    "report_type": sched.report_type.value,
                    "rows": len(report.rows),
                    "summary": report.summary,
                }
            )
        for tenant_id, retention_days in retention_tenants.items():
            pruned += (await self.prune_runs(retention_days=retention_days, tenant_id=tenant_id))[
                "removed"
            ]
        await self._record_audit(
            tenant_id=None,
            action="report.run_due",
            payload={"generated": len(reports), "pruned": pruned},
        )
        return {
            "run_at": now.isoformat(),
            "generated": len(reports),
            "pruned": pruned,
            "reports": reports,
        }
