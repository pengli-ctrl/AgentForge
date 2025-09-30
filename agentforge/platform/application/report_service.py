from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from agentforge.platform.domain.reporting import (
    OperationsReport,
    ReportFormat,
    ReportRun,
    ReportType,
    ScheduledReport,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_run_for(cadence: str, last_run: datetime) -> datetime:
    """Advance next_run_at by the schedule cadence (naive label)."""
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
    ) -> None:
        self._cost = cost_repository
        self._audit = audit_repository
        self._regression = regression_repository
        self._schedules = schedule_repository
        self._runs = run_repository

    async def _persist(self, report: OperationsReport) -> ReportRun:
        run = ReportRun.from_operations(report)
        await self._runs.save(run)
        return run

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
        return report

    async def list_runs(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        items = await self._runs.list(
            tenant_id=tenant_id,
            report_type=report_type.value if isinstance(report_type, ReportType) else report_type,
            limit=limit,
        )
        return [self._run_meta(i) for i in items]

    async def get_run(self, run_id: str) -> ReportRun | None:
        return await self._runs.get(run_id)

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
    ) -> ScheduledReport:
        report_id = report_id or uuid.uuid4().hex[:16]
        now = _now()
        sched = ScheduledReport(
            report_id=report_id,
            tenant_id=tenant_id,
            report_type=report_type,
            cadence=cadence,
            enabled=True,
            created_at=now,
            last_run_at=None,
            next_run_at=now,
        )
        await self._schedules.save(sched)
        return sched

    async def list_schedules(self, tenant_id: str | None = None, limit: int = 100) -> list[dict]:
        items = await self._schedules.list_schedules(tenant_id=tenant_id, limit=limit)
        return [i.model_dump(mode="json") for i in items]

    async def delete_schedule(self, report_id: str) -> None:
        await self._schedules.delete(report_id)

    async def run_due(self, fmt: ReportFormat = ReportFormat.JSON) -> dict:
        """Generate reports for all due schedules and advance next_run_at.

        Idempotent: each due schedule is generated exactly once and its
        next_run_at is advanced, so a repeated invocation won't regenerate
        unless the schedule has become due again.
        """
        now = _now()
        due = await self._schedules.list_due(before=now)
        reports = []
        for sched in due:
            report = await self.generate(
                report_type=sched.report_type,
                tenant_id=sched.tenant_id,
                fmt=fmt,
                scheduled_report_id=sched.report_id,
            )
            sched.last_run_at = now
            sched.next_run_at = _next_run_for(sched.cadence, now)
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
        return {"run_at": now.isoformat(), "generated": len(reports), "reports": reports}
