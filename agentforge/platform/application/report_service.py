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
    return datetime.now(timezone.utc)


def _advance_next_run(cadence: str, last_run: datetime) -> datetime:
    """Advance next_run_at by the schedule cadence.

    Supports simplified labels (daily / weekly / monthly) and standard 5-field
    cron expressions (e.g. "0 2 * * *"); the cron form computes the next match
    strictly after the last run.
    """
    if is_cron_cadence(cadence):
        return CronSchedule(cadence).next_run_from(last_run=last_run, now=_now())
    if cadence == "weekly":
        return last_run + timedelta(days=7)
    if cadence == "monthly":
        return last_run + timedelta(days=30)
    return last_run + timedelta(days=1)  # daily (default)


class ReportService:
    """Operational report generation and scheduling.

    Aggregates cost / audit / quality data into row-oriented exports (JSON or
    CSV) and manages recurring schedules (due detection + next_run advance).
    Successful generations are persisted as immutable report runs for later
    historical retrieval. Delegates to injected repositories so it works on
    both memory and SQLAlchemy backends.
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
        self._cost = cost_repository
        self._audit = audit_repository
        self._regression = regression_repository
        self._schedules = schedule_repository
        self._runs = run_repository
        # Global default retention window applied to due schedules that do not
        # define an explicit retention_days, so auto-prune never leaves history
        # unbounded even when an operator didn't configure per-schedule policy.
        self._default_retention_days = default_retention_days

    async def _persist(self, report: OperationsReport) -> ReportRun:
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
        report_id = report_id or uuid.uuid4().hex[:16]
        if report_type == ReportType.COST:
            rows, summary = await self._build_cost(tenant_id, days)
        elif report_type == ReportType.AUDIT:
            rows, summary = await self._build_audit(tenant_id)
        else:  # QUALITY
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
        items, next_cursor = await self._runs.list_page(
            tenant_id=tenant_id,
            report_type=report_type.value if isinstance(report_type, ReportType) else report_type,
            limit=limit,
            archived=archived,
            cursor=cursor,
        )
        return [self._run_meta(i) for i in items], next_cursor

    async def get_run(self, run_id: str) -> ReportRun | None:
        return await self._runs.get(run_id)

    async def archive_run(self, run_id: str, archived: bool) -> dict:
        """Mark (or unmark) a persisted report run as archived.

        Archived runs are excluded from the default (active) listing but
        retained for compliance / later retrieval.
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
        """Bundle persisted report runs into an in-memory ZIP archive.

        Convenience wrapper over :meth:`_write_archive` that buffers the ZIP
        into memory and returns raw bytes plus an ArchiveInfo JSON payload.
        For large archives prefer :meth:`export_archive_to` with a disk sink
        so the payload is streamed and not held in memory.
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
        """Bundle persisted report runs into a ZIP written to ``sink``.

        ``sink`` must be a writeable binary file object (e.g. an open temp
        file). The ZIP is written incrementally so the full archive never
        needs to be buffered in memory. Returns the ArchiveInfo JSON payload.
        """
        return await self._write_archive(sink, tenant_id=tenant_id, limit=limit)

    async def _write_archive(self, sink, tenant_id: str | None = None, limit: int = 100) -> str:
        """Serialize persisted runs into a ZIP written to ``sink``.

        Each run is serialized in its native format (JSON/CSV) into a file
        named ``run_{run_id}.{ext}`` under the archive. Returns the
        ArchiveInfo JSON payload describing the bundled files.
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
        """Delete report runs older than retention_days (retention policy).

        By default archived runs are preserved (archiving is an intent to retain
        for compliance); pass ``include_archived=True`` to also remove them.
        Returns summary of removed count. Runs with enabled retention policy
        (older than the threshold) are removed so historical runs don't accrue
        unbounded.
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

    # --- schedule management ---

    async def schedule(
        self,
        tenant_id: str,
        report_type: ReportType,
        cadence: str = "daily",
        report_id: str | None = None,
        retention_days: int | None = None,
    ) -> ScheduledReport:
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
        items = await self._schedules.list_schedules(tenant_id=tenant_id, limit=limit)
        return [i.model_dump(mode="json") for i in items]

    async def delete_schedule(self, report_id: str) -> None:
        sched = await self._schedules.get(report_id)
        await self._schedules.delete(report_id)
        await self._record_audit(
            tenant_id=sched.tenant_id if sched is not None else None,
            action="report.schedule.delete",
            resource_id=report_id,
        )

    async def set_schedule_enabled(self, report_id: str, enabled: bool) -> ScheduledReport:
        """Pause (disabled) or resume (enabled) a report schedule.

        Disabled schedules are skipped by list_due / run_due so they no longer
        generate runs, without deleting the schedule or losing its config.
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
        """Generate reports for all due schedules and advance next_run_at.

        Idempotent: each due schedule is generated exactly once and its
        next_run_at is advanced, so a repeated invocation won't regenerate
        unless the schedule has become due again. After generation, old runs
        for each affected tenant are pruned per the schedule's retention
        policy (retention_days); schedules without an explicit policy fall
        back to the service/global default retention window so history doesn't
        accrue unbounded.
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
                # keep the strictest (smallest) retention per tenant
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
