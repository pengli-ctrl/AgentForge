"""AgentForge 平台 API 层：console_router。

本模块定义 console_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_console_router。
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from agentforge.platform.application.ports import CostRepository
from agentforge.platform.domain.connector import spec_to_public_dict
from agentforge.platform.domain.cron import CronExpressionError, CronSchedule, is_cron_cadence
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
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        quota_repository: Any，调用方传入的 quota_repository 参数。
        cost_repository: CostRepository | None，调用方传入的 cost_repository 参数。
        outbox_store: Any，调用方传入的 outbox_store 参数。
        audit_repository: Any，调用方传入的 audit_repository 参数。
        ticket_repository: Any，调用方传入的 ticket_repository 参数。
        dashboard_service: Any，调用方传入的 dashboard_service 参数。
        connector_registry: Any，调用方传入的 connector_registry 参数。
        connector_repository: Any，调用方传入的 connector_repository 参数。
        authenticator: Any，调用方传入的 authenticator 参数。
        report_service: Any，调用方传入的 report_service 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1/console", tags=["console"])

    @router.get("/overview")
    async def overview(tenant_id: str) -> dict:
        """执行 overview 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        result: dict = {"tenant_id": tenant_id}

        # 验证配额控制，确保预算和硬限额生效。
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

        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        if ticket_repository is not None:
            result["tasks"] = await _status_counts(ticket_repository, tenant_id)

        # 验证失败场景，确保异常路径能够被正确处理。
        if outbox_store is not None:
            failed = await outbox_store.list_failed(limit=50)
            result["dlq"] = {"failed_count": len(failed)}
        else:
            result["dlq"] = {"failed_count": 0}

        # 验证审计记录，确保关键行为可追踪。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。
            status: str | None，调用方传入的 status 参数。
            limit: int，调用方传入的 limit 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """执行 approval_inbox 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """执行 costs_overview 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """执行 cost_trend 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            days: int，调用方传入的 days 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        days = max(1, min(days, 365))
        return await dashboard_service.cost_trend(tenant_id, days=days)

    @router.get("/model-distribution")
    async def model_distribution(tenant_id: str) -> dict:
        """执行 model_distribution 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        return await dashboard_service.model_distribution(tenant_id)

    @router.get("/quality")
    async def quality(tenant_id: str, limit: int = 10) -> dict:
        """执行 quality 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        return await dashboard_service.quality_metrics(tenant_id, limit=limit)

    @router.get("/traces")
    async def traces(tenant_id: str | None = None, limit: int = 50) -> dict:
        """执行 traces 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        return await dashboard_service.recent_traces(tenant_id=tenant_id, limit=limit)

    @router.get("/dashboard")
    async def dashboard(tenant_id: str) -> dict:
        """执行 dashboard 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。
            action: str | None，调用方传入的 action 参数。
            actor_id: str | None，调用方传入的 actor_id 参数。
            resource_id: str | None，调用方传入的 resource_id 参数。
            resource_type: str | None，调用方传入的 resource_type 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if connector_repository is None:
            raise HTTPException(status_code=503, detail="Connector repository is not configured")
        specs = await connector_repository.list_specs(tenant_id=None)
        rows = []
        for spec in specs:
            row = spec_to_public_dict(spec)
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
        """执行 set_connector_enabled 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            connector_id: str，调用方传入的 connector_id 参数。
            body: dict，调用方传入的 body 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if connector_repository is None:
            raise HTTPException(status_code=503, detail="Connector repository is not configured")
        spec = await connector_repository.get_spec(connector_id)
        if spec is None:
            raise HTTPException(status_code=404, detail="connector not found")
        spec.enabled = bool(body.get("enabled", True))
        await connector_repository.save_spec(spec)
        return spec_to_public_dict(spec)

    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。

    @router.get("/reports/export")
    async def export_report(
        request: Request,
        report_type: str = "cost",
        tenant_id: str = "default",
        format: str = "json",
        days: int = 30,
    ) -> Response:
        """执行 export_report 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            report_type: str，调用方传入的 report_type 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。
            format: str，调用方传入的 format 参数。
            days: int，调用方传入的 days 参数。

        Returns:
            Response，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """创建新的业务对象，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            body: dict，调用方传入的 body 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        try:
            rtype = ReportType(body.get("report_type", "cost"))
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid report_type")
        tenant_id = str(body.get("tenant_id", "default"))
        cadence = str(body.get("cadence", "daily"))
        if is_cron_cadence(cadence):
            try:
                CronSchedule(cadence)
            except CronExpressionError:
                raise HTTPException(status_code=400, detail="invalid cadence cron expression")
        elif cadence not in ("daily", "weekly", "monthly"):
            raise HTTPException(status_code=400, detail="invalid cadence")
        retention_days = body.get("retention_days")
        if retention_days is not None:
            try:
                retention_days = int(retention_days)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="invalid retention_days")
        schedule = await report_service.schedule(
            tenant_id=tenant_id,
            report_type=rtype,
            cadence=cadence,
            retention_days=retention_days,
        )
        return schedule.model_dump(mode="json")

    @router.get("/reports/schedules")
    async def list_schedules(request: Request, tenant_id: str | None = None) -> dict:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        schedules = await report_service.list_schedules(tenant_id=tenant_id)
        return {"schedules": schedules}

    @router.delete("/reports/schedule/{report_id}")
    async def delete_schedule(request: Request, report_id: str) -> dict:
        """删除指定数据，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            report_id: str，调用方传入的 report_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        await report_service.delete_schedule(report_id)
        return {"deleted": report_id}

    @router.post("/reports/schedule/{report_id}/enabled")
    async def set_schedule_enabled(request: Request, report_id: str, body: dict) -> dict:
        """执行 set_schedule_enabled 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            report_id: str，调用方传入的 report_id 参数。
            body: dict，调用方传入的 body 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        enabled = bool(body.get("enabled", True))
        try:
            sched = await report_service.set_schedule_enabled(report_id, enabled)
        except KeyError:
            raise HTTPException(status_code=404, detail="schedule not found")
        return sched.model_dump(mode="json")

    @router.post("/reports/run-due")
    async def run_due(request: Request, body: dict = {}) -> dict:
        """执行完整流程，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            body: dict，调用方传入的 body 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        default_retention_days = body.get("default_retention_days")
        if default_retention_days is not None:
            try:
                default_retention_days = int(default_retention_days)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="invalid default_retention_days")
        return await report_service.run_due(default_retention_days=default_retention_days)

    @router.get("/reports/runs")
    async def list_runs(
        request: Request,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
        cursor: str | None = None,
    ) -> dict:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            report_type: str | None，调用方传入的 report_type 参数。
            limit: int，调用方传入的 limit 参数。
            archived: bool | None，调用方传入的 archived 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        runs, next_cursor = await report_service.list_runs_paginated(
            tenant_id=tenant_id,
            report_type=report_type,
            limit=limit,
            archived=archived,
            cursor=cursor,
        )
        return {"runs": runs, "next_cursor": next_cursor}

    @router.post("/reports/runs/{run_id}/archive")
    async def archive_run(request: Request, run_id: str, body: dict) -> dict:
        """执行 archive_run 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            run_id: str，调用方传入的 run_id 参数。
            body: dict，调用方传入的 body 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        archived = bool(body.get("archived", True))
        try:
            return await report_service.archive_run(run_id, archived=archived)
        except KeyError:
            raise HTTPException(status_code=404, detail="report run not found")

    @router.get("/reports/runs/archive")
    async def export_archive(
        request: Request,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> Response:
        """执行 export_archive 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            Response，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        fd, path = tempfile.mkstemp(suffix=".zip")
        with os.fdopen(fd, "wb") as sink:
            await report_service.export_archive_to(sink, tenant_id=tenant_id, limit=limit)
        headers = {"Content-Disposition": 'attachment; filename="report_runs_archive.zip"'}

        def _iter_zip() -> Iterator[bytes]:
            """执行 _iter_zip 对应的逻辑，并返回处理结果。

            Returns:
                Iterator[bytes]，函数执行后的结果。
            """
            try:
                with open(path, "rb") as f:
                    while chunk := f.read(64 * 1024):
                        yield chunk
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass

        return StreamingResponse(_iter_zip(), media_type="application/zip", headers=headers)

    @router.get("/reports/runs/{run_id}")
    async def get_run(
        request: Request,
        run_id: str,
        format: str = "json",
    ) -> Response:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            run_id: str，调用方传入的 run_id 参数。
            format: str，调用方传入的 format 参数。

        Returns:
            Response，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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

    @router.post("/reports/runs/prune")
    async def prune_runs(request: Request, body: dict) -> dict:
        """执行 prune_runs 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            body: dict，调用方传入的 body 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        retention_days = int(body.get("retention_days", 30))
        tenant_id = body.get("tenant_id")
        include_archived = bool(body.get("include_archived", False))
        return await report_service.prune_runs(
            retention_days=retention_days,
            tenant_id=tenant_id,
            include_archived=include_archived,
        )

    return router


def _authorize_admin(authenticator, request: Request) -> None:
    """执行 _authorize_admin 对应的逻辑，并返回处理结果。

    Args:
        authenticator: Any，调用方传入的 authenticator 参数。
        request: Request，调用方传入的 request 参数。

    Returns:
        None，函数执行后的结果。
    """
    if authenticator is not None:
        authenticator.authorize_admin(request)


async def _status_counts(ticket_repository, tenant_id: str) -> dict:
    """执行 _status_counts 对应的逻辑，并返回处理结果。

    Args:
        ticket_repository: Any，调用方传入的 ticket_repository 参数。
        tenant_id: str，调用方传入的 tenant_id 参数。

    Returns:
        dict，函数执行后的结果。
    """
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
    """执行 _list_tenant_ids 对应的逻辑，并返回处理结果。

    Args:
        quota_repository: Any，调用方传入的 quota_repository 参数。
        cost_repository: Any，调用方传入的 cost_repository 参数。

    Returns:
        list[str]，函数执行后的结果。
    """
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
    """执行 _ticket_summary 对应的逻辑，并返回处理结果。

    Args:
        t: Any，调用方传入的 t 参数。

    Returns:
        dict，函数执行后的结果。
    """
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
