from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from agentforge.platform.application.ports import CostRepository
from agentforge.platform.domain.reporting import ReportFormat, ReportType
from agentforge.platform.domain.tenant_quota import TenantQuota


def create_console_router(
    quota_repository=None,
    cost_repository: CostRepository | None = None,
    outbox_store=None,
    audit_repository=None,
    ticket_repository=None,
    dashboard_service=None,
    connector_registry=None,
    connector_repository=None,
    authenticator=None,
    report_service=None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/console", tags=["console"])

    @router.get("/overview")
    async def overview(tenant_id: str) -> dict:
        result: dict = {"tenant_id": tenant_id}

        # Quota & spend
        quota: TenantQuota | None = None
        if quota_repository is not None:
            quota = await quota_repository.get(tenant_id)
        used = 0.0
        if cost_repository is not None:
            used = await cost_repository.total_for_tenant(tenant_id)
        if quota is not None:
            result["quota"] = quota.model_dump(mode="json")
            result["quota"]["configured"] = True
            result["quota"]["usage"] = quota.usage_status(used)
        else:
            result["quota"] = {"configured": False, "used": used}
        result["cost"] = {"used": used}

        # Task status counts (support agent workbench)
        if ticket_repository is not None:
            result["tasks"] = await _status_counts(ticket_repository, tenant_id)

        # DLQ failed count
        if outbox_store is not None:
            failed = await outbox_store.list_failed(limit=50)
            result["dlq"] = {"failed_count": len(failed)}
        else:
            result["dlq"] = {"failed_count": 0}

        # Recent audit events (entries only, not payload)
        if audit_repository is not None:
            events = await audit_repository.list_events(tenant_id, limit=20)
            result["audit"] = {
                "recent_count": len(events),
                "recent": [
                    {
                        "event_id": e.event_id,
                        "action": e.action,
                        "resource_type": e.resource_type,
                        "resource_id": e.resource_id,
                        "occurred_at": e.occurred_at.isoformat(),
                    }
                    for e in events
                ],
            }
        else:
            result["audit"] = {"recent_count": 0, "recent": []}

        return result

    @router.get("/tickets")
    async def list_tickets(
        request: Request,
        tenant_id: str,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict:
        if ticket_repository is None:
            raise HTTPException(status_code=503, detail="Ticket repository is not configured")
        tickets, next_cursor = await ticket_repository.list(
            tenant_id, status=status, limit=limit, cursor=cursor
        )
        return {
            "tenant_id": tenant_id,
            "tickets": [_ticket_summary(t) for t in tickets],
            "next_cursor": next_cursor,
        }

    @router.get("/inbox")
    async def approval_inbox(
        request: Request, tenant_id: str, limit: int = 100, cursor: str | None = None
    ) -> dict:
        if ticket_repository is None:
            raise HTTPException(status_code=503, detail="Ticket repository is not configured")
        tickets, next_cursor = await ticket_repository.list(
            tenant_id, status="waiting_approval", limit=limit, cursor=cursor
        )
        return {
            "tenant_id": tenant_id,
            "items": [_ticket_summary(t) for t in tickets],
            "next_cursor": next_cursor,
        }

    @router.get("/costs")
    async def costs_overview(request: Request) -> dict:
        """Admin multi-tenant cost / quota summary. Admin-only."""
        if quota_repository is None or cost_repository is None:
            raise HTTPException(
                status_code=503, detail="Cost or quota repository is not configured"
            )
        tenants = await _list_tenant_ids(quota_repository, cost_repository)
        rows = []
        total = 0.0
        for tenant_id in tenants:
            used = await cost_repository.total_for_tenant(tenant_id)
            total += used
            quota = await quota_repository.get(tenant_id)
            row: dict = {"tenant_id": tenant_id, "used": used}
            if quota is not None:
                row["quota"] = quota.model_dump(mode="json")
                row["quota"]["configured"] = True
                row["quota"]["usage"] = quota.usage_status(used)
            else:
                row["quota"] = {"configured": False}
            rows.append(row)
        return {"tenants": rows, "total_cost": total}

    @router.get("/cost-trend")
    async def cost_trend(tenant_id: str, days: int = 30) -> dict:
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        days = max(1, min(days, 365))
        return await dashboard_service.cost_trend(tenant_id, days=days)

    @router.get("/model-distribution")
    async def model_distribution(tenant_id: str) -> dict:
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        return await dashboard_service.model_distribution(tenant_id)

    @router.get("/quality")
    async def quality(tenant_id: str, limit: int = 10) -> dict:
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        return await dashboard_service.quality_metrics(tenant_id, limit=limit)

    @router.get("/dashboard")
    async def dashboard(tenant_id: str) -> dict:
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        trend = await dashboard_service.cost_trend(tenant_id, days=30)
        distribution = await dashboard_service.model_distribution(tenant_id)
        quota = await dashboard_service.quota_snapshot(tenant_id)
        quality = await dashboard_service.quality_metrics(tenant_id)
        return {
            "tenant_id": tenant_id,
            "cost_trend": trend,
            "model_distribution": distribution,
            "quota": quota,
            "quality": quality,
        }

    @router.get("/tenants")
    async def list_tenants(request: Request) -> dict:
        """Admin multi-tenant config: quota + usage + enabled state."""
        _authorize_admin(authenticator, request)
        if cost_repository is None:
            raise HTTPException(status_code=503, detail="Cost repository is not configured")
        tenant_ids = await _list_tenant_ids(quota_repository, cost_repository)
        rows = []
        for tenant_id in tenant_ids:
            row: dict = {"tenant_id": tenant_id}
            used = await cost_repository.total_for_tenant(tenant_id)
            row["used"] = used
            quota = None
            if quota_repository is not None:
                quota = await quota_repository.get(tenant_id)
            if quota is not None:
                row["quota"] = quota.model_dump(mode="json")
                row["quota"]["configured"] = True
                row["quota"]["usage"] = quota.usage_status(used)
                row["enabled"] = quota.enabled
            else:
                row["quota"] = {"configured": False}
                row["enabled"] = True
            rows.append(row)
        return {"tenants": rows}

    @router.get("/audit")
    async def list_audit(
        request: Request,
        tenant_id: str | None = None,
        limit: int = 100,
        action: str | None = None,
        actor_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
        cursor: str | None = None,
    ) -> dict:
        """Admin audit query across tenants."""
        _authorize_admin(authenticator, request)
        if audit_repository is None:
            raise HTTPException(status_code=503, detail="Audit repository is not configured")
        events, next_cursor = await audit_repository.query_events(
            tenant_id=tenant_id,
            limit=limit,
            action=action,
            actor_id=actor_id,
            resource_id=resource_id,
            resource_type=resource_type,
            cursor=cursor,
        )
        return {
            "events": [event.model_dump(mode="json") for event in events],
            "next_cursor": next_cursor,
        }

    @router.get("/connectors")
    async def list_connectors(request: Request) -> dict:
        """Admin connector management: persisted specs + health."""
        _authorize_admin(authenticator, request)
        if connector_repository is None:
            raise HTTPException(status_code=503, detail="Connector repository is not configured")
        specs = await connector_repository.list_specs(tenant_id=None)
        rows = []
        for spec in specs:
            row = spec.model_dump(mode="json")
            if connector_registry is not None:
                health = await connector_registry.health(spec.connector_id)
                row["health"] = health.model_dump(mode="json") if health is not None else None
            rows.append(row)
        return {"connectors": rows}

    @router.post("/connectors/{connector_id}/enabled")
    async def set_connector_enabled(
        request: Request,
        connector_id: str,
        body: dict,
    ) -> dict:
        """Enable/disable a connector. Persists to connector repository."""
        _authorize_admin(authenticator, request)
        if connector_repository is None:
            raise HTTPException(status_code=503, detail="Connector repository is not configured")
        spec = await connector_repository.get_spec(connector_id)
        if spec is None:
            raise HTTPException(status_code=404, detail="connector not found")
        spec.enabled = bool(body.get("enabled", True))
        await connector_repository.save_spec(spec)
        return spec.model_dump(mode="json")

    # --- operational reports (export + scheduling) ---

    @router.get("/reports/export")
    async def export_report(
        request: Request,
        report_type: str = "cost",
        tenant_id: str = "default",
        format: str = "json",
        days: int = 30,
    ) -> Response:
        """Admin on-demand operational report export (JSON or CSV)."""
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        try:
            rtype = ReportType(report_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid report_type")
        fmt = ReportFormat(format)
        report = await report_service.generate(
            report_type=rtype, tenant_id=tenant_id, fmt=fmt, days=days
        )
        if fmt == ReportFormat.CSV:
            payload = report.to_csv()
            headers = {"Content-Disposition": f'attachment; filename="report_{rtype.value}.csv"'}
            return Response(content=payload, media_type="text/csv", headers=headers)
        return Response(
            content=report.to_json(),
            media_type="application/json",
        )

    @router.post("/reports/schedule")
    async def create_schedule(request: Request, body: dict) -> dict:
        """Admin create a recurring report schedule."""
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        try:
            rtype = ReportType(body.get("report_type", "cost"))
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid report_type")
        tenant_id = str(body.get("tenant_id", "default"))
        cadence = str(body.get("cadence", "daily"))
        schedule = await report_service.schedule(
            tenant_id=tenant_id, report_type=rtype, cadence=cadence
        )
        return schedule.model_dump(mode="json")

    @router.get("/reports/schedules")
    async def list_schedules(request: Request, tenant_id: str | None = None) -> dict:
        """Admin list report schedules (optionally filtered by tenant)."""
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        schedules = await report_service.list_schedules(tenant_id=tenant_id)
        return {"schedules": schedules}

    @router.delete("/reports/schedule/{report_id}")
    async def delete_schedule(request: Request, report_id: str) -> dict:
        """Admin delete a report schedule."""
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        await report_service.delete_schedule(report_id)
        return {"deleted": report_id}

    @router.post("/reports/run-due")
    async def run_due(request: Request) -> dict:
        """Admin run all due report schedules (idempotent, advances next_run)."""
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        return await report_service.run_due()

    @router.get("/reports/runs")
    async def list_runs(
        request: Request,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Admin list persisted operational report runs (newest first)."""
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        runs = await report_service.list_runs(
            tenant_id=tenant_id,
            report_type=report_type,
            limit=limit,
        )
        return {"runs": runs}

    @router.get("/reports/runs/{run_id}")
    async def get_run(
        request: Request,
        run_id: str,
        format: str = "json",
    ) -> Response:
        """Admin retrieve a persisted report run as JSON or CSV."""
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        run = await report_service.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="report run not found")
        fmt = ReportFormat(format)
        if fmt == ReportFormat.CSV:
            headers = {"Content-Disposition": f'attachment; filename="run_{run_id}.csv"'}
            return Response(content=run.to_csv(), media_type="text/csv", headers=headers)
        return Response(content=run.to_json(), media_type="application/json")

    return router


def _authorize_admin(authenticator, request: Request) -> None:
    if authenticator is not None:
        authenticator.authorize_admin(request)


async def _status_counts(ticket_repository, tenant_id: str) -> dict:
    counts: dict[str, int] = {}
    for status in (
        "new",
        "classifying",
        "waiting_review",
        "waiting_approval",
        "ready_to_publish",
        "published",
        "escalated",
        "failed",
        "cancelled",
    ):
        tickets, _ = await ticket_repository.list(tenant_id, status=status, limit=1000)
        counts[status] = len(tickets)
    return counts


async def _list_tenant_ids(quota_repository, cost_repository) -> list[str]:
    """Determine tenant ids for admin cost overview: union of cost record tenants
    and configured quota tenants (dedup, keep stable order)."""
    ids: dict[str, None] = {}
    if hasattr(cost_repository, "list_tenants"):
        try:
            for tid in await cost_repository.list_tenants():
                ids.setdefault(tid, None)
        except Exception:
            pass
    try:
        for quota in await quota_repository.list():
            ids.setdefault(quota.tenant_id, None)
    except Exception:
        pass
    return list(ids.keys())


def _ticket_summary(t) -> dict:
    return {
        "ticket_id": t.ticket_id,
        "status": t.status,
        "priority": t.priority,
        "subject": t.subject,
        "intent": t.intent,
        "product": t.product,
        "assigned_team": t.assigned_team,
        "risk_level": t.risk_level,
        "confidence": t.confidence,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }
